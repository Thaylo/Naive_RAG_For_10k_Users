from fastapi import FastAPI, HTTPException, BackgroundTasks
import httpx
import asyncio
from typing import Dict, List
import uuid
import os
from datetime import datetime
from contextlib import asynccontextmanager
import queue
import threading

from shared.models.task import Task, TaskStatus
from shared.models.chunk import Chunk
from shared.models.embedding import Embedding
from shared.utils.mock_llm import MockEmbeddingLLM
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class EmbeddingService:
    def __init__(self):
        self.logger = setup_logger("embedding-service", os.getenv("LOG_LEVEL", "INFO"))
        self.embeddings_queue = queue.Queue(maxsize=1000)
        self.worker_id = str(uuid.uuid4())
        self.master_task_db_url = os.getenv("MASTER_TASK_DB_URL", "http://master-task-db:8001")
        # Support multiple chunking services
        chunking_urls = os.getenv("CHUNKING_SERVICE_URLS", "http://chunking-1:8004,http://chunking-2:8004")
        self.chunking_service_urls = [url.strip() for url in chunking_urls.split(",")]
        self.running = True
        self.llm = MockEmbeddingLLM()
        self.processing_tasks = set()
        self.logger.info(f"EmbeddingService initialized. Worker ID: {self.worker_id}")
        self.logger.info(f"URLs - Master: {self.master_task_db_url}, Chunking: {self.chunking_service_urls}")
    
    async def start(self):
        # Create a task processor for each chunking service
        for url in self.chunking_service_urls:
            asyncio.create_task(self.process_tasks_from_service(url))
        asyncio.create_task(self.heartbeat_loop())
    
    async def process_tasks_from_service(self, chunking_url: str):
        """Process tasks using a specific chunking service"""
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    self.logger.debug("Checking for CHUNKED tasks...")
                    response = await client.get(
                        f"{self.master_task_db_url}/tasks/status/{TaskStatus.CHUNKED.value}"
                    )
                    self.logger.debug(f"Status check response: {response.status_code}")
                    
                    if response.status_code == 200:
                        tasks = response.json()
                        self.logger.info(f"Found {len(tasks)} tasks with CHUNKED status")
                        for task_data in tasks:
                            task = Task(**task_data)
                            if not task.worker_id and task.id not in self.processing_tasks:
                                await self.process_single_task(task, client, chunking_url)
                
                except Exception as e:
                    log_error(self.logger, e, "process_tasks")
                
                await asyncio.sleep(5)
    
    async def process_single_task(self, task: Task, client: httpx.AsyncClient, chunking_url: str):
        self.processing_tasks.add(task.id)
        try:
            self.logger.info(f"Processing task {task.id} for embedding")
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.EMBEDDING.value, "worker_id": self.worker_id}
            )
            self.logger.debug(f"Task {task.id} status updated to EMBEDDING")
            
            self.logger.info(f"Fetching chunks for task {task.id}")
            chunks_response = await client.get(f"{chunking_url}/chunks/{task.id}")
            if chunks_response.status_code != 200:
                self.logger.error(f"Chunks not found for task {task.id}: {chunks_response.status_code}")
                raise Exception("Chunks not found")
            
            chunks_data = chunks_response.json()["chunks"]
            chunks = [Chunk(**chunk_data) for chunk_data in chunks_data]
            self.logger.info(f"Found {len(chunks)} chunks for task {task.id}")
            
            embeddings = await self.generate_embeddings(chunks)
            self.logger.info(f"Generated {len(embeddings)} embeddings for task {task.id}")
            
            for embedding in embeddings:
                try:
                    self.embeddings_queue.put(embedding.dict(), timeout=1)
                except queue.Full:
                    self.logger.warning(f"Embeddings queue full for task {task.id}")
            
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.EMBEDDED.value}
            )
            self.logger.info(f"Task {task.id} marked as EMBEDDED")
            
            await client.delete(f"{chunking_url}/chunks/{task.id}")
            self.logger.info(f"Cleared chunks for task {task.id}")
            
        except Exception as e:
            log_error(self.logger, e, f"process_single_task for {task.id}")
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.FAILED.value}
            )
            self.logger.info(f"Task {task.id} marked as FAILED")
        finally:
            self.processing_tasks.discard(task.id)
    
    async def generate_embeddings(self, chunks: List[Chunk]) -> List[Embedding]:
        embeddings = []
        
        texts = [chunk.content for chunk in chunks]
        vectors = self.llm.generate_embeddings(texts)
        
        for chunk, vector in zip(chunks, vectors):
            embedding = Embedding(
                id=f"{chunk.id}_emb",
                chunk_id=chunk.id,
                task_id=chunk.task_id,
                vector=vector,
                model_name="mock-embedding-model",
                dimension=len(vector)
            )
            embeddings.append(embedding)
        
        return embeddings
    
    async def heartbeat_loop(self):
        async with httpx.AsyncClient() as client:
            while self.running:
                for task_id in list(self.processing_tasks):
                    try:
                        await client.post(
                            f"{self.master_task_db_url}/tasks/{task_id}/heartbeat",
                            params={"worker_id": self.worker_id}
                        )
                    except Exception:
                        pass
                
                await asyncio.sleep(10)
    
    def get_embeddings(self, batch_size: int = 10) -> List[dict]:
        embeddings = []
        for _ in range(batch_size):
            try:
                embedding = self.embeddings_queue.get_nowait()
                embeddings.append(embedding)
            except queue.Empty:
                break
        return embeddings


embedding_service = EmbeddingService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await embedding_service.start()
    yield
    embedding_service.running = False


app = FastAPI(title="Embedding Service", lifespan=lifespan)


@app.get("/embeddings/batch")
async def get_embeddings_batch(batch_size: int = 10):
    log_request(embedding_service.logger, "GET", "/embeddings/batch", batch_size=batch_size)
    embeddings = embedding_service.get_embeddings(batch_size)
    log_response(embedding_service.logger, "GET", "/embeddings/batch", 200, count=len(embeddings))
    return {"embeddings": embeddings, "count": len(embeddings)}


@app.get("/queue/status")
async def queue_status():
    log_request(embedding_service.logger, "GET", "/queue/status")
    status = {
        "queue_size": embedding_service.embeddings_queue.qsize(),
        "max_size": embedding_service.embeddings_queue.maxsize,
        "processing_tasks": list(embedding_service.processing_tasks)
    }
    log_response(embedding_service.logger, "GET", "/queue/status", 200)
    return status


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "embedding", "worker_id": embedding_service.worker_id}