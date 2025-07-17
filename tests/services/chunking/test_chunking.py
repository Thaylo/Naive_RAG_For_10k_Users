import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock, MagicMock
import tempfile
import os

from services.chunking.main import app, chunking_service, ChunkingService
from shared.models.task import Task, TaskStatus
from shared.models.chunk import Chunk, ChunkConfig


@pytest.fixture
def client():
    chunking_service.chunks_buffer.clear()
    return TestClient(app)


@pytest.fixture
def sample_pdf_content():
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000262 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
356
%%EOF"""


class TestChunkingService:
    def test_initialization(self):
        service = ChunkingService()
        assert service.chunks_buffer == {}
        assert service.chunk_config.chunk_size == 1000
        assert service.chunk_config.overlap_percentage == 0.1
        assert service.running is True
    
    @pytest.mark.asyncio
    async def test_fetch_chunk_config(self):
        service = ChunkingService()
        
        with patch('services.chunking.main.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "chunk_size": 2000,
                "overlap_percentage": 0.2,
                "strategy": "fixed_size"
            }
            mock_client.get.return_value = mock_response
            
            await service.fetch_chunk_config()
            
            assert service.chunk_config.chunk_size == 2000
            assert service.chunk_config.overlap_percentage == 0.2
    
    @pytest.mark.asyncio
    async def test_chunk_pdf_success(self, sample_pdf_content):
        service = ChunkingService()
        service.chunk_config = ChunkConfig(chunk_size=100, overlap_percentage=0.1)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(sample_pdf_content)
            tmp_path = tmp.name
        
        try:
            with patch('services.chunking.main.PdfReader') as mock_pdf_reader:
                mock_page = Mock()
                mock_page.extract_text.return_value = "This is a test PDF document with some content that needs to be chunked properly."
                mock_reader = Mock()
                mock_reader.pages = [mock_page]
                mock_pdf_reader.return_value = mock_reader
                
                chunks = await service.chunk_pdf("task123", tmp_path)
                
                assert len(chunks) > 0
                assert all(isinstance(chunk, Chunk) for chunk in chunks)
                assert all(chunk.task_id == "task123" for chunk in chunks)
                
                for i, chunk in enumerate(chunks):
                    assert chunk.chunk_index == i
                    assert chunk.start_char >= 0
                    assert chunk.end_char > chunk.start_char
        finally:
            os.unlink(tmp_path)
    
    @pytest.mark.asyncio
    async def test_chunk_pdf_with_overlap(self):
        service = ChunkingService()
        service.chunk_config = ChunkConfig(chunk_size=100, overlap_percentage=0.5)
        
        with patch('services.chunking.main.PdfReader') as mock_pdf_reader:
            mock_page = Mock()
            mock_page.extract_text.return_value = "A" * 200
            mock_reader = Mock()
            mock_reader.pages = [mock_page]
            mock_pdf_reader.return_value = mock_reader
            
            chunks = await service.chunk_pdf("task123", "dummy.pdf")
            
            assert len(chunks) >= 2
            
            if len(chunks) > 1:
                first_chunk_end = chunks[0].end_char
                second_chunk_start = chunks[1].start_char
                overlap = first_chunk_end - second_chunk_start
                assert overlap == 50
    
    def test_get_and_clear_chunks(self):
        service = chunking_service
        
        test_chunks = [
            Chunk(
                id="chunk1",
                task_id="task123",
                content="Test content",
                chunk_index=0,
                start_char=0,
                end_char=12
            )
        ]
        
        service.chunks_buffer["task123"] = test_chunks
        
        retrieved = service.get_chunks("task123")
        assert retrieved == test_chunks
        
        service.clear_chunks("task123")
        assert "task123" not in service.chunks_buffer
        
        assert service.get_chunks("non-existent") == []


class TestAPI:
    def test_get_chunks_endpoint(self, client):
        test_chunks = [
            Chunk(
                id="chunk1",
                task_id="task123",
                content="Test content 1",
                chunk_index=0,
                start_char=0,
                end_char=14
            ),
            Chunk(
                id="chunk2",
                task_id="task123",
                content="Test content 2",
                chunk_index=1,
                start_char=14,
                end_char=28
            )
        ]
        
        chunking_service.chunks_buffer["task123"] = test_chunks
        
        response = client.get("/chunks/task123")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task123"
        assert len(data["chunks"]) == 2
        assert data["chunks"][0]["content"] == "Test content 1"
        
        response = client.get("/chunks/non-existent")
        assert response.status_code == 404
    
    def test_clear_chunks_endpoint(self, client):
        test_chunks = [
            Chunk(
                id="chunk1",
                task_id="task123",
                content="Test",
                chunk_index=0,
                start_char=0,
                end_char=4
            )
        ]
        
        chunking_service.chunks_buffer["task123"] = test_chunks
        
        response = client.delete("/chunks/task123")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"
        assert response.json()["task_id"] == "task123"
        
        assert "task123" not in chunking_service.chunks_buffer
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "chunking"
        assert "worker_id" in data