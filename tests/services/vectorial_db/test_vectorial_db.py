import pytest
from fastapi.testclient import TestClient
import numpy as np
from unittest.mock import patch, Mock, AsyncMock

from services.vectorial_db.main import app, vector_service, VectorDatabase
from shared.models.embedding import Embedding


@pytest.fixture
def client():
    vector_service.db = VectorDatabase()
    return TestClient(app)


@pytest.fixture
def sample_embeddings():
    embeddings = []
    for i in range(5):
        emb = Embedding(
            id=f"emb_{i}",
            chunk_id=f"chunk_{i}",
            task_id="task_123" if i < 3 else "task_456",
            vector=[float(j) for j in np.random.randn(384)],
            model_name="mock-model",
            dimension=384
        )
        embeddings.append(emb)
    return embeddings


class TestVectorDatabase:
    def test_add_embedding(self):
        db = VectorDatabase()
        embedding = Embedding(
            id="test_emb",
            chunk_id="test_chunk",
            task_id="test_task",
            vector=[0.1] * 384,
            model_name="test-model",
            dimension=384
        )
        
        db.add_embedding(embedding)
        
        assert "test_emb" in db.vectors
        assert np.array_equal(db.vectors["test_emb"], np.array([0.1] * 384))
        assert "test_emb" in db.metadata
        assert db.metadata["test_emb"]["chunk_id"] == "test_chunk"
        assert db.metadata["test_emb"]["task_id"] == "test_task"
        assert "test_task" in db.task_embeddings
        assert "test_emb" in db.task_embeddings["test_task"]
    
    def test_search_empty_database(self):
        db = VectorDatabase()
        results = db.search([0.1] * 384, top_k=5)
        assert results == []
    
    def test_search_with_results(self, sample_embeddings):
        db = VectorDatabase()
        
        for emb in sample_embeddings:
            db.add_embedding(emb)
        
        query_vector = [0.1] * 384
        results = db.search(query_vector, top_k=3)
        
        assert len(results) <= 3
        for result in results:
            assert "embedding_id" in result
            assert "score" in result
            assert "metadata" in result
            assert -1 <= result["score"] <= 1
    
    def test_search_with_task_filter(self, sample_embeddings):
        db = VectorDatabase()
        
        for emb in sample_embeddings:
            db.add_embedding(emb)
        
        query_vector = [0.1] * 384
        results = db.search(query_vector, top_k=5, task_ids=["task_123"])
        
        assert len(results) <= 3
        for result in results:
            assert result["metadata"]["task_id"] == "task_123"
    
    def test_get_stats(self, sample_embeddings):
        db = VectorDatabase()
        
        for emb in sample_embeddings:
            db.add_embedding(emb)
        
        stats = db.get_stats()
        
        assert stats["total_embeddings"] == 5
        assert stats["total_tasks"] == 2
        assert "task_123" in stats["tasks"]
        assert "task_456" in stats["tasks"]


class TestVectorDatabaseService:
    @pytest.mark.asyncio
    @patch('services.vectorial_db.main.httpx.AsyncClient')
    async def test_consume_embeddings(self, mock_httpx_client, sample_embeddings):
        service = vector_service
        mock_client = AsyncMock()
        
        embeddings_data = {
            "embeddings": [emb.dict() for emb in sample_embeddings[:2]]
        }
        mock_embeddings_response = Mock(status_code=200)
        mock_embeddings_response.json.return_value = embeddings_data
        
        mock_update_response = Mock(status_code=200)
        
        mock_client.get.return_value = mock_embeddings_response
        mock_client.put.return_value = mock_update_response
        
        service.running = False
        
        await service.consume_embeddings()
        
        assert len(service.db.vectors) == 0


class TestAPI:
    def test_search_endpoint(self, client, sample_embeddings):
        service = vector_service
        
        for emb in sample_embeddings:
            service.db.add_embedding(emb)
        
        query_vector = [0.1] * 384
        
        response = client.post("/search", json={
            "query_vector": query_vector,
            "top_k": 3
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 3
        
        response = client.post("/search", json={
            "query_vector": query_vector,
            "top_k": 5,
            "task_ids": ["task_123"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 3
        for result in data["results"]:
            assert result["metadata"]["task_id"] == "task_123"
    
    def test_stats_endpoint(self, client, sample_embeddings):
        service = vector_service
        
        for emb in sample_embeddings:
            service.db.add_embedding(emb)
        
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_embeddings"] == 5
        assert data["total_tasks"] == 2
        assert len(data["tasks"]) == 2
    
    def test_get_task_embeddings_endpoint(self, client, sample_embeddings):
        service = vector_service
        
        for emb in sample_embeddings:
            service.db.add_embedding(emb)
        
        response = client.get("/embeddings/task_123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert len(data["embeddings"]) == 3
        
        response = client.get("/embeddings/non_existent_task")
        assert response.status_code == 404
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "vectorial_db"