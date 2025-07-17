from fastapi import FastAPI, HTTPException, BackgroundTasks
import httpx
import asyncio
from typing import Dict, List
import uuid
import os
from datetime import datetime
import aiofiles
from pypdf import PdfReader
from contextlib import asynccontextmanager

from shared.models.task import Task, TaskStatus
from shared.models.chunk import Chunk, ChunkConfig
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class ChunkingService:
    def __init__(self):
        self.logger = setup_logger("chunking-service", os.getenv("LOG_LEVEL", "INFO"))
        self.chunks_buffer: Dict[str, List[Chunk]] = {}
        self.worker_id = str(uuid.uuid4())
        self.chunk_config = ChunkConfig()
        self.master_task_db_url = os.getenv("MASTER_TASK_DB_URL", "http://master-task-db:8001")
        self.chunk_config_url = os.getenv("CHUNK_CONFIG_URL", "http://chunk-config:8002")
        self.upload_service_url = os.getenv("UPLOAD_SERVICE_URL", "http://upload:8003")
        self.running = True
        self.logger.info(f"ChunkingService initialized. Worker ID: {self.worker_id}")
        self.logger.info(f"URLs - Master: {self.master_task_db_url}, Config: {self.chunk_config_url}, Upload: {self.upload_service_url}")
    
    async def start(self):
        await self.subscribe_to_config()
        await self.fetch_chunk_config()
        asyncio.create_task(self.process_tasks())
        asyncio.create_task(self.heartbeat_loop())
    
    async def subscribe_to_config(self):
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{self.chunk_config_url}/subscribe",
                    params={"service_id": self.worker_id}
                )
            except Exception as e:
                print(f"Failed to subscribe to config: {e}")
    
    async def fetch_chunk_config(self):
        async with httpx.AsyncClient() as client:
            try:
                self.logger.info("Fetching chunk configuration...")
                response = await client.get(f"{self.chunk_config_url}/config")
                if response.status_code == 200:
                    self.chunk_config = ChunkConfig(**response.json())
                    self.logger.info(f"Chunk config updated: size={self.chunk_config.chunk_size}, overlap={self.chunk_config.overlap_percentage}")
                else:
                    self.logger.error(f"Failed to fetch chunk config: {response.status_code}")
            except Exception as e:
                log_error(self.logger, e, "fetch_chunk_config")
    
    async def process_tasks(self):
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    self.logger.debug("Checking for UPLOAD_COMPLETED tasks...")
                    response = await client.get(
                        f"{self.master_task_db_url}/tasks/status/{TaskStatus.UPLOAD_COMPLETED.value}"
                    )
                    self.logger.debug(f"Status check response: {response.status_code}")
                    
                    if response.status_code == 200:
                        tasks = response.json()
                        self.logger.info(f"Found {len(tasks)} tasks with UPLOAD_COMPLETED status")
                        for task_data in tasks:
                            task = Task(**task_data)
                            if not task.worker_id:
                                await self.process_single_task(task, client)
                
                except Exception as e:
                    log_error(self.logger, e, "process_tasks")
                
                await asyncio.sleep(5)
    
    async def process_single_task(self, task: Task, client: httpx.AsyncClient):
        try:
            self.logger.info(f"Processing task {task.id} for file: {task.filename}")
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.CHUNKING.value, "worker_id": self.worker_id}
            )
            self.logger.debug(f"Task {task.id} status updated to CHUNKING")
            
            self.logger.info(f"Fetching file path for task {task.id}")
            file_response = await client.get(f"{self.upload_service_url}/file/{task.id}")
            if file_response.status_code != 200:
                self.logger.error(f"File not found for task {task.id}: {file_response.status_code}")
                raise Exception("File not found")
            
            file_path = file_response.json()["file_path"]
            
            # Determine file type and chunk accordingly
            if file_path.lower().endswith('.pdf'):
                self.logger.info(f"Chunking PDF file: {file_path}")
                chunks = await self.chunk_pdf(task.id, file_path)
            elif file_path.lower().endswith('.txt'):
                self.logger.info(f"Chunking text file: {file_path}")
                chunks = await self.chunk_text(task.id, file_path)
            else:
                self.logger.error(f"Unsupported file type for {file_path}")
                raise Exception(f"Unsupported file type")
            
            self.chunks_buffer[task.id] = chunks
            self.logger.info(f"Created {len(chunks)} chunks for task {task.id}")
            
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.CHUNKED.value, "worker_id": None}
            )
            self.logger.info(f"Task {task.id} marked as CHUNKED")
            
        except Exception as e:
            log_error(self.logger, e, f"process_single_task for {task.id}")
            await client.put(
                f"{self.master_task_db_url}/tasks/{task.id}/status",
                params={"status": TaskStatus.FAILED.value}
            )
            self.logger.info(f"Task {task.id} marked as FAILED")
    
    async def chunk_pdf(self, task_id: str, file_path: str) -> List[Chunk]:
        chunks = []
        
        try:
            reader = PdfReader(file_path)
            full_text = ""
            
            for page in reader.pages:
                full_text += page.extract_text() + "\n"
            
            chunk_size = self.chunk_config.chunk_size
            overlap_size = int(chunk_size * self.chunk_config.overlap_percentage)
            
            start = 0
            chunk_index = 0
            
            while start < len(full_text):
                end = min(start + chunk_size, len(full_text))
                chunk_text = full_text[start:end]
                
                chunk = Chunk(
                    id=f"{task_id}_chunk_{chunk_index}",
                    task_id=task_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end
                )
                chunks.append(chunk)
                
                start = end - overlap_size if end < len(full_text) else end
                chunk_index += 1
                
        except Exception as e:
            print(f"Error chunking PDF: {e}")
            
        return chunks
    
    async def chunk_text(self, task_id: str, file_path: str) -> List[Chunk]:
        chunks = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            
            chunk_size = self.chunk_config.chunk_size
            overlap_size = int(chunk_size * self.chunk_config.overlap_percentage)
            
            start = 0
            chunk_index = 0
            
            while start < len(full_text):
                end = min(start + chunk_size, len(full_text))
                chunk_text = full_text[start:end]
                
                chunk = Chunk(
                    id=f"{task_id}_chunk_{chunk_index}",
                    task_id=task_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end
                )
                chunks.append(chunk)
                
                start = end - overlap_size if end < len(full_text) else end
                chunk_index += 1
                
        except Exception as e:
            print(f"Error chunking text file: {e}")
            
        return chunks
    
    async def heartbeat_loop(self):
        async with httpx.AsyncClient() as client:
            while self.running:
                for task_id in list(self.chunks_buffer.keys()):
                    try:
                        await client.post(
                            f"{self.master_task_db_url}/tasks/{task_id}/heartbeat",
                            params={"worker_id": self.worker_id}
                        )
                    except Exception:
                        pass
                
                await asyncio.sleep(10)
    
    def get_chunks(self, task_id: str) -> List[Chunk]:
        return self.chunks_buffer.get(task_id, [])
    
    def clear_chunks(self, task_id: str):
        if task_id in self.chunks_buffer:
            del self.chunks_buffer[task_id]


chunking_service = ChunkingService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await chunking_service.start()
    yield
    chunking_service.running = False


app = FastAPI(title="Chunking Service", lifespan=lifespan)


@app.get("/chunks/{task_id}")
async def get_chunks(task_id: str):
    chunks = chunking_service.get_chunks(task_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="Chunks not found")
    return {"task_id": task_id, "chunks": [chunk.dict() for chunk in chunks]}


@app.delete("/chunks/{task_id}")
async def clear_chunks(task_id: str):
    chunking_service.clear_chunks(task_id)
    return {"status": "cleared", "task_id": task_id}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "chunking", "worker_id": chunking_service.worker_id}