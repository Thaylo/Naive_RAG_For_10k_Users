import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
import os
import tempfile
from io import BytesIO

from services.upload.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_httpx_client():
    with patch('services.upload.main.httpx.AsyncClient') as mock:
        yield mock


@pytest.fixture
def pdf_file():
    pdf_content = b"%PDF-1.4\n%Test PDF content"
    return ("test.pdf", BytesIO(pdf_content), "application/pdf")


@pytest.fixture
def non_pdf_file():
    return ("test.txt", BytesIO(b"Not a PDF"), "text/plain")


class TestUploadAPI:
    @patch('services.upload.main.aiofiles.open')
    def test_upload_single_pdf_success(self, mock_aiofiles_module, client, mock_httpx_client, pdf_file):
        # Mock do contexto manager do aiofiles
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()
        
        mock_aiofiles_context = AsyncMock()
        mock_aiofiles_context.__aenter__.return_value = mock_file
        mock_aiofiles_context.__aexit__.return_value = None
        
        mock_aiofiles_module.return_value = mock_aiofiles_context
        
        # Mock do httpx client
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_create_task_response = Mock()
        mock_create_task_response.status_code = 200
        mock_create_task_response.json.return_value = {"id": "task-123", "filename": "test.pdf"}
        mock_client.post.return_value = mock_create_task_response
        
        mock_update_status_response = Mock()
        mock_update_status_response.status_code = 200
        mock_client.put.return_value = mock_update_status_response
        
        response = client.post("/upload", files={"files": pdf_file})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "success"
        assert data["results"][0]["filename"] == "test.pdf"
        assert data["results"][0]["task_id"] == "task-123"
    
    def test_upload_no_files(self, client):
        response = client.post("/upload")
        assert response.status_code == 422
    
    def test_upload_non_pdf_file(self, client, non_pdf_file):
        response = client.post("/upload", files={"files": non_pdf_file})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "error"
        assert "Only PDF files are allowed" in data["results"][0]["message"]
    
    @patch('services.upload.main.aiofiles.open')
    def test_upload_multiple_files(self, mock_aiofiles_module, client, mock_httpx_client, pdf_file, non_pdf_file):
        # Mock do contexto manager do aiofiles
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()
        
        mock_aiofiles_context = AsyncMock()
        mock_aiofiles_context.__aenter__.return_value = mock_file
        mock_aiofiles_context.__aexit__.return_value = None
        
        mock_aiofiles_module.return_value = mock_aiofiles_context
        
        # Mock do httpx client
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_create_task_response = Mock()
        mock_create_task_response.status_code = 200
        mock_create_task_response.json.return_value = {"id": "task-123", "filename": "test.pdf"}
        mock_client.post.return_value = mock_create_task_response
        
        mock_update_status_response = Mock()
        mock_update_status_response.status_code = 200
        mock_client.put.return_value = mock_update_status_response
        
        response = client.post("/upload", files=[("files", pdf_file), ("files", non_pdf_file)])
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert data["results"][0]["status"] == "success"
        assert data["results"][1]["status"] == "error"
    
    @patch('services.upload.main.aiofiles.open')
    def test_upload_task_creation_failure(self, mock_aiofiles_module, client, mock_httpx_client, pdf_file):
        # Mock do contexto manager do aiofiles
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()
        
        mock_aiofiles_context = AsyncMock()
        mock_aiofiles_context.__aenter__.return_value = mock_file
        mock_aiofiles_context.__aexit__.return_value = None
        
        mock_aiofiles_module.return_value = mock_aiofiles_context
        
        # Mock do httpx client
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        mock_create_task_response = Mock()
        mock_create_task_response.status_code = 500
        mock_client.post.return_value = mock_create_task_response
        
        response = client.post("/upload", files={"files": pdf_file})
        
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "Failed to create task" in data["results"][0]["message"]
    
    @patch('services.upload.main.aiofiles.open')
    def test_upload_file_write_error(self, mock_aiofiles_module, client, mock_httpx_client, pdf_file):
        # Mock do aiofiles para lançar erro
        mock_aiofiles_module.side_effect = IOError("Disk full")
        
        # Mock do httpx client
        mock_client = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client
        
        response = client.post("/upload", files={"files": pdf_file})
        
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "Disk full" in data["results"][0]["message"]
    
    @patch('services.upload.main.aiofiles.open')
    @patch('services.upload.main.os.path.exists', return_value=True)
    def test_get_file_path_success(self, mock_exists, mock_aiofiles_module, client):
        # Mock do contexto manager do aiofiles
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value="/app/storage/uploads/file123_test.pdf")
        
        mock_aiofiles_context = AsyncMock()
        mock_aiofiles_context.__aenter__.return_value = mock_file
        mock_aiofiles_context.__aexit__.return_value = None
        
        mock_aiofiles_module.return_value = mock_aiofiles_context
        
        response = client.get("/file/task-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
        assert data["file_path"] == "/app/storage/uploads/file123_test.pdf"
    
    @patch('services.upload.main.os.path.exists', return_value=False)
    def test_get_file_path_not_found(self, mock_exists, client):
        response = client.get("/file/non-existent")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"
    
    def test_health_check(self, client):
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "upload"