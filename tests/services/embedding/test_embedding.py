import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
import queue

from services.embedding.main import app, embedding_service
from shared.models.chunk import Chunk
from shared.models.embedding import Embedding


@pytest.fixture
def client():
    embedding_service.embeddings_queue = queue.Queue(maxsize=1000)
    embedding_service.processing_tasks.clear()
    return TestClient(app)


@pytest.fixture
def sample_chunks():
    return [
        Chunk(
            id="chunk1",
            task_id="task123",
            content="This is the first chunk",
            chunk_index=0,
            start_char=0,
            end_char=100
        ),
        Chunk(
            id="chunk2",
            task_id="task123",
            content="This is the second chunk",
            chunk_index=1,
            start_char=100,
            end_char=200
        )
    ]


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_generate_embeddings(self, sample_chunks):
        service = embedding_service
        embeddings = await service.generate_embeddings(sample_chunks)
        
        assert len(embeddings) == 2
        for i, embedding in enumerate(embeddings):
            assert embedding.chunk_id == sample_chunks[i].id
            assert embedding.task_id == "task123"
            assert len(embedding.vector) == 384
            assert embedding.model_name == "mock-embedding-model"
    
    def test_get_embeddings_from_queue(self):
        service = embedding_service
        
        sample_embeddings = [
            {"id": f"emb{i}", "vector": [0.1] * 384}
            for i in range(5)
        ]
        
        for emb in sample_embeddings:
            service.embeddings_queue.put(emb)
        
        result = service.get_embeddings(batch_size=3)
        assert len(result) == 3
        
        result = service.get_embeddings(batch_size=10)
        assert len(result) == 2
        
        result = service.get_embeddings(batch_size=10)
        assert len(result) == 0
    
    @pytest.mark.asyncio
    @patch('services.embedding.main.httpx.AsyncClient')
    async def test_process_single_task_success(self, mock_httpx_client, sample_chunks):
        service = embedding_service
        mock_client = AsyncMock()
        
        mock_update_response = Mock(status_code=200)
        mock_client.put.return_value = mock_update_response
        
        chunks_data = {"chunks": [chunk.dict() for chunk in sample_chunks]}
        mock_chunks_response = Mock(status_code=200)
        mock_chunks_response.json.return_value = chunks_data
        mock_client.get.return_value = mock_chunks_response
        
        mock_delete_response = Mock(status_code=200)
        mock_client.delete.return_value = mock_delete_response
        
        from shared.models.task import Task, TaskStatus
        task = Task(id="task123", filename="test.pdf", status=TaskStatus.CHUNKED)
        
        await service.process_single_task(task, mock_client)
        
        assert service.embeddings_queue.qsize() == 2
        assert "task123" not in service.processing_tasks
        
        assert mock_client.put.call_count == 2
        first_call_params = mock_client.put.call_args_list[0][1]["params"]
        assert first_call_params["status"] == TaskStatus.EMBEDDING
        
        last_call_params = mock_client.put.call_args_list[-1][1]["params"]
        assert last_call_params["status"] == TaskStatus.EMBEDDED
    
    @pytest.mark.asyncio
    @patch('services.embedding.main.httpx.AsyncClient')
    async def test_process_single_task_chunks_not_found(self, mock_httpx_client):
        service = embedding_service
        mock_client = AsyncMock()
        
        mock_update_response = Mock(status_code=200)
        mock_client.put.return_value = mock_update_response
        
        mock_chunks_response = Mock(status_code=404)
        mock_client.get.return_value = mock_chunks_response
        
        from shared.models.task import Task, TaskStatus
        task = Task(id="task123", filename="test.pdf", status=TaskStatus.CHUNKED)
        
        await service.process_single_task(task, mock_client)
        
        last_call_params = mock_client.put.call_args_list[-1][1]["params"]
        assert last_call_params["status"] == TaskStatus.FAILED


class TestAPI:
    def test_get_embeddings_batch_endpoint(self, client):
        service = embedding_service
        
        sample_embeddings = [
            {"id": f"emb{i}", "vector": [0.1] * 384}
            for i in range(15)
        ]
        
        for emb in sample_embeddings:
            service.embeddings_queue.put(emb)
        
        response = client.get("/embeddings/batch?batch_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 10
        assert len(data["embeddings"]) == 10
        
        response = client.get("/embeddings/batch?batch_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5
        assert len(data["embeddings"]) == 5
    
    def test_queue_status_endpoint(self, client):
        service = embedding_service
        
        for i in range(5):
            service.embeddings_queue.put({"id": f"emb{i}"})
        
        service.processing_tasks.add("task1")
        service.processing_tasks.add("task2")
        
        response = client.get("/queue/status")
        assert response.status_code == 200
        data = response.json()
        assert data["queue_size"] == 5
        assert data["max_size"] == 1000
        assert len(data["processing_tasks"]) == 2
        assert "task1" in data["processing_tasks"]
        assert "task2" in data["processing_tasks"]
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "embedding"
        assert "worker_id" in response.json()