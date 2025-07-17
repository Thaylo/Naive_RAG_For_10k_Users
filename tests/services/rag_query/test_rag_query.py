import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock

from services.rag_query.main import app, rag_service
from shared.utils.mock_llm import MockEmbeddingLLM, MockChatLLM


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_query_request():
    return {
        "query": "What is the meaning of life?",
        "task_ids": ["task123"],
        "top_k": 3
    }


@pytest.fixture
def sample_search_results():
    return [
        {
            "embedding_id": "emb1",
            "score": 0.95,
            "metadata": {
                "chunk_id": "chunk1",
                "task_id": "task123",
                "model_name": "mock-model"
            }
        },
        {
            "embedding_id": "emb2",
            "score": 0.87,
            "metadata": {
                "chunk_id": "chunk2",
                "task_id": "task123",
                "model_name": "mock-model"
            }
        }
    ]


class TestRAGQueryService:
    def test_embedding_llm_initialization(self):
        service = rag_service
        assert isinstance(service.embedding_llm, MockEmbeddingLLM)
        assert isinstance(service.chat_llm, MockChatLLM)
    
    @pytest.mark.asyncio
    @patch('services.rag_query.main.httpx.AsyncClient')
    async def test_process_query_success(self, mock_httpx_client, sample_query_request, sample_search_results):
        service = rag_service
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {"results": sample_search_results}
        
        mock_chunks_response = Mock()
        mock_chunks_response.status_code = 200
        mock_chunks_response.json.return_value = {
            "chunks": [
                {
                    "id": "chunk1",
                    "content": "The meaning of life is 42"
                },
                {
                    "id": "chunk2",
                    "content": "According to Douglas Adams"
                }
            ]
        }
        
        mock_client.post.return_value = mock_search_response
        mock_client.get.return_value = mock_chunks_response
        
        from services.rag_query.main import QueryRequest
        query_req = QueryRequest(**sample_query_request)
        response = await service.process_query(query_req)
        
        assert response.query == sample_query_request["query"]
        assert response.response is not None
        assert len(response.sources) <= 3
        assert response.sources[0]["chunk_id"] == "chunk1"
        assert response.sources[0]["score"] == 0.95
    
    @pytest.mark.asyncio
    @patch('services.rag_query.main.httpx.AsyncClient')
    async def test_process_query_no_results(self, mock_httpx_client, sample_query_request):
        service = rag_service
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {"results": []}
        
        mock_client.post.return_value = mock_search_response
        
        from services.rag_query.main import QueryRequest
        query_req = QueryRequest(**sample_query_request)
        response = await service.process_query(query_req)
        
        assert response.query == sample_query_request["query"]
        assert response.response is not None
        assert len(response.sources) == 0
    
    @pytest.mark.asyncio
    @patch('services.rag_query.main.httpx.AsyncClient')
    async def test_process_query_search_failure(self, mock_httpx_client, sample_query_request):
        service = rag_service
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_search_response = Mock()
        mock_search_response.status_code = 500
        mock_client.post.return_value = mock_search_response
        
        from services.rag_query.main import QueryRequest
        query_req = QueryRequest(**sample_query_request)
        
        with pytest.raises(Exception):
            await service.process_query(query_req)


class TestAPI:
    @patch('services.rag_query.main.httpx.AsyncClient')
    def test_query_endpoint_success(self, mock_httpx_client, client, sample_query_request, sample_search_results):
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {"results": sample_search_results}
        
        mock_chunks_response = Mock()
        mock_chunks_response.status_code = 200
        mock_chunks_response.json.return_value = {
            "chunks": [
                {
                    "id": "chunk1",
                    "content": "Test content"
                }
            ]
        }
        
        mock_client.post.return_value = mock_search_response
        mock_client.get.return_value = mock_chunks_response
        
        response = client.post("/query", json=sample_query_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == sample_query_request["query"]
        assert "response" in data
        assert "sources" in data
    
    def test_query_endpoint_validation(self, client):
        invalid_requests = [
            {},
            {"query": ""},
            {"query": "test", "top_k": -1},
            {"query": "test", "top_k": "not a number"}
        ]
        
        for invalid_req in invalid_requests:
            response = client.post("/query", json=invalid_req)
            assert response.status_code in [422, 500]
    
    @patch('services.rag_query.main.httpx.AsyncClient')
    def test_query_endpoint_internal_error(self, mock_httpx_client, client, sample_query_request):
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_client.post.side_effect = Exception("Connection error")
        
        response = client.post("/query", json=sample_query_request)
        
        assert response.status_code == 500
        assert "Connection error" in response.json()["detail"]
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "rag_query"


class TestMockLLMs:
    def test_mock_embedding_llm(self):
        llm = MockEmbeddingLLM(dimension=384)
        
        text = "Test text"
        embedding = llm.generate_embedding(text)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)
        
        same_embedding = llm.generate_embedding(text)
        assert embedding == same_embedding
        
        embeddings = llm.generate_embeddings(["text1", "text2"])
        assert len(embeddings) == 2
        assert all(len(emb) == 384 for emb in embeddings)
    
    def test_mock_chat_llm(self):
        llm = MockChatLLM()
        
        response = llm.generate_response("Hello")
        assert "mockado" in response or "greeting" in response
        
        response = llm.generate_response("Test", "Context info")
        assert "Context" in response or "contexto" in response