from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime
import os
from contextlib import asynccontextmanager

from shared.models.task import TaskStatus
from shared.models.embedding import Embedding
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class VectorDatabase:
    def __init__(self):
        self.vectors: Dict[str, np.ndarray] = {}
        self.metadata: Dict[str, dict] = {}
        self.task_embeddings: Dict[str, List[str]] = {}
    
    def add_embedding(self, embedding: Embedding):
        self.vectors[embedding.id] = np.array(embedding.vector)
        self.metadata[embedding.id] = {
            "chunk_id": embedding.chunk_id,
            "task_id": embedding.task_id,
            "model_name": embedding.model_name,
            "dimension": embedding.dimension,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if embedding.task_id not in self.task_embeddings:
            self.task_embeddings[embedding.task_id] = []
        self.task_embeddings[embedding.task_id].append(embedding.id)
    
    def search(self, query_vector: List[float], top_k: int = 5, task_ids: Optional[List[str]] = None) -> List[dict]:
        if not self.vectors:
            return []
        
        query_np = np.array(query_vector).reshape(1, -1)
        
        if task_ids:
            relevant_ids = []
            for task_id in task_ids:
                relevant_ids.extend(self.task_embeddings.get(task_id, []))
        else:
            relevant_ids = list(self.vectors.keys())
        
        if not relevant_ids:
            return []
        
        vectors_matrix = np.array([self.vectors[id] for id in relevant_ids])
        # Compute cosine similarity manually
        # cosine_similarity = (A·B) / (||A|| * ||B||)
        dot_products = np.dot(vectors_matrix, query_np.T).flatten()
        query_norm = np.linalg.norm(query_np)
        vector_norms = np.linalg.norm(vectors_matrix, axis=1)
        similarities = dot_products / (query_norm * vector_norms + 1e-10)  # Add small epsilon to avoid division by zero
        
        # Limit top_k to the actual number of relevant embeddings
        actual_top_k = min(top_k, len(relevant_ids))
        top_indices = np.argsort(similarities)[-actual_top_k:][::-1]
        
        results = []
        for idx in top_indices:
            embedding_id = relevant_ids[idx]
            results.append({
                "embedding_id": embedding_id,
                "score": float(similarities[idx]),
                "metadata": self.metadata[embedding_id]
            })
        
        return results
    
    def get_stats(self) -> dict:
        return {
            "total_embeddings": len(self.vectors),
            "total_tasks": len(self.task_embeddings),
            "tasks": list(self.task_embeddings.keys())
        }


class VectorDatabaseService:
    def __init__(self):
        self.logger = setup_logger("vectorial-db-service", os.getenv("LOG_LEVEL", "INFO"))
        self.db = VectorDatabase()
        self.master_task_db_url = os.getenv("MASTER_TASK_DB_URL", "http://master-task-db:8001")
        
        # Support multiple embedding services
        embedding_urls = os.getenv("EMBEDDING_SERVICE_URLS", "http://embedding-1:8005,http://embedding-2:8005")
        self.embedding_service_urls = [url.strip() for url in embedding_urls.split(",")]
        
        self.running = True
        self.logger.info(f"VectorDatabaseService initialized")
        self.logger.info(f"Master DB URL: {self.master_task_db_url}")
        self.logger.info(f"Embedding Service URLs: {self.embedding_service_urls}")
    
    async def start(self):
        # Create a consumer task for each embedding service
        for url in self.embedding_service_urls:
            asyncio.create_task(self.consume_embeddings_from_service(url))
    
    async def consume_embeddings_from_service(self, service_url: str):
        """Consume embeddings from a specific embedding service"""
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    self.logger.debug(f"Fetching embeddings batch from {service_url}...")
                    response = await client.get(
                        f"{service_url}/embeddings/batch",
                        params={"batch_size": 50}
                    )
                    self.logger.debug(f"Embeddings batch response from {service_url}: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        embeddings = data.get("embeddings", [])
                        
                        if embeddings:
                            self.logger.info(f"Processing {len(embeddings)} embeddings from {service_url}")
                        
                        for emb_data in embeddings:
                            embedding = Embedding(**emb_data)
                            self.db.add_embedding(embedding)
                            self.logger.debug(f"Added embedding {embedding.id} for task {embedding.task_id}")
                            
                            await client.put(
                                f"{self.master_task_db_url}/tasks/{embedding.task_id}/status",
                                params={"status": TaskStatus.VECTORIZED.value}
                            )
                            self.logger.info(f"Task {embedding.task_id} marked as VECTORIZED")
                
                except Exception as e:
                    log_error(self.logger, e, f"consume_embeddings from {service_url}")
                
                await asyncio.sleep(2)


vector_service = VectorDatabaseService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await vector_service.start()
    yield
    vector_service.running = False


app = FastAPI(title="Vectorial Database Service", lifespan=lifespan)


@app.post("/search")
async def search_embeddings(
    query_vector: List[float],
    top_k: int = 5,
    task_ids: Optional[List[str]] = None
):
    log_request(vector_service.logger, "POST", "/search", top_k=top_k, task_ids=task_ids)
    results = vector_service.db.search(query_vector, top_k, task_ids)
    log_response(vector_service.logger, "POST", "/search", 200, results_count=len(results))
    return {"results": results}


@app.get("/stats")
async def get_database_stats():
    log_request(vector_service.logger, "GET", "/stats")
    stats = vector_service.db.get_stats()
    log_response(vector_service.logger, "GET", "/stats", 200)
    return stats


@app.get("/embeddings/{task_id}")
async def get_task_embeddings(task_id: str):
    log_request(vector_service.logger, "GET", f"/embeddings/{task_id}")
    embedding_ids = vector_service.db.task_embeddings.get(task_id, [])
    if not embedding_ids:
        vector_service.logger.warning(f"No embeddings found for task {task_id}")
        raise HTTPException(status_code=404, detail="No embeddings found for task")
    
    embeddings = []
    for emb_id in embedding_ids:
        embeddings.append({
            "id": emb_id,
            "metadata": vector_service.db.metadata[emb_id]
        })
    
    log_response(vector_service.logger, "GET", f"/embeddings/{task_id}", 200, embeddings_count=len(embeddings))
    return {"task_id": task_id, "embeddings": embeddings}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "vectorial_db"}