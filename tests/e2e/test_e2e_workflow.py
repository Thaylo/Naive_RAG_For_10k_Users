import pytest
import httpx
import asyncio
import time
from typing import Dict, List
import os
import tempfile

# Service URLs
NGINX_URL = "http://localhost:8080"
MASTER_TASK_DB_URL = "http://localhost:8001"
CHUNK_CONFIG_URL = "http://localhost:8002"
UPLOAD_URL = "http://localhost:8003"
RAG_QUERY_URL = "http://localhost:8007"
VECTORIAL_DB_URL = "http://localhost:8006"


class TestE2EWorkflow:
    """End-to-end tests for the complete RAG pipeline"""
    
    @pytest.fixture(scope="class")
    def sample_pdf_content(self):
        """Create a simple PDF content for testing"""
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
<< /Length 200 >>
stream
BT
/F1 12 Tf
100 700 Td
(This is a test PDF document for the RAG system. It contains information about artificial intelligence and machine learning. The system should be able to chunk and embed this content properly.) Tj
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
500
%%EOF"""

    def test_01_all_services_healthy(self):
        """Test that all services are healthy"""
        services = [
            (MASTER_TASK_DB_URL, "master_task_db"),
            (CHUNK_CONFIG_URL, "chunk_config"),
            (UPLOAD_URL, "upload"),
            (RAG_QUERY_URL, "rag_query"),
            (VECTORIAL_DB_URL, "vectorial_db")
        ]
        
        for url, service_name in services:
            response = httpx.get(f"{url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == service_name

    def test_02_nginx_proxy_working(self):
        """Test that nginx proxy is correctly routing requests"""
        proxy_tests = [
            ("/chunk-config/health", "chunk_config"),
            ("/upload/health", "upload"),
            ("/rag/health", "rag_query")
        ]
        
        for path, expected_service in proxy_tests:
            response = httpx.get(f"{NGINX_URL}{path}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == expected_service

    def test_03_documentation_endpoints(self):
        """Test that all documentation endpoints are accessible"""
        doc_endpoints = [
            f"{NGINX_URL}/chunk-config/docs",
            f"{NGINX_URL}/upload/docs",
            f"{NGINX_URL}/rag/docs",
            f"{MASTER_TASK_DB_URL}/docs",
            f"{CHUNK_CONFIG_URL}/docs",
            f"{UPLOAD_URL}/docs",
            f"{RAG_QUERY_URL}/docs",
            f"{VECTORIAL_DB_URL}/docs"
        ]
        
        for endpoint in doc_endpoints:
            response = httpx.get(endpoint)
            assert response.status_code == 200
            assert "Swagger UI" in response.text

    def test_04_configure_chunking(self):
        """Test chunk configuration update"""
        config_data = {
            "chunk_size": 500,
            "overlap_percentage": 0.2
        }
        
        response = httpx.put(
            f"{NGINX_URL}/chunk-config/config",
            json=config_data
        )
        assert response.status_code == 200
        
        # Verify configuration was updated
        response = httpx.get(f"{NGINX_URL}/chunk-config/config")
        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 500
        assert data["overlap_percentage"] == 0.2

    def test_05_complete_pdf_workflow(self, sample_pdf_content):
        """Test the complete workflow: upload -> chunk -> embed -> query"""
        
        # Step 1: Upload PDF
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(sample_pdf_content)
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, 'rb') as f:
                files = {'files': ('test.pdf', f, 'application/pdf')}
                response = httpx.post(f"{NGINX_URL}/upload/upload", files=files)
            
            assert response.status_code == 200
            upload_data = response.json()
            assert len(upload_data["results"]) == 1
            assert upload_data["results"][0]["status"] == "success"
            task_id = upload_data["results"][0]["task_id"]
            
            # Step 2: Wait for processing (check task status)
            max_attempts = 30
            for attempt in range(max_attempts):
                response = httpx.get(f"{MASTER_TASK_DB_URL}/tasks/{task_id}")
                if response.status_code == 200:
                    task_data = response.json()
                    if task_data["status"] == "VECTORIZED":
                        break
                    elif task_data["status"] == "FAILED":
                        pytest.fail(f"Task failed: {task_data}")
                time.sleep(2)
            else:
                pytest.fail("Task did not complete in time")
            
            # Step 3: Query the system
            query_data = {
                "query": "What information does this document contain about AI?"
            }
            response = httpx.post(f"{NGINX_URL}/rag/query", json=query_data)
            assert response.status_code == 200
            
            rag_response = response.json()
            assert "response" in rag_response
            assert len(rag_response["chunks"]) > 0
            
        finally:
            os.unlink(tmp_path)

    def test_06_multiple_tasks_concurrent(self, sample_pdf_content):
        """Test handling multiple concurrent uploads"""
        
        # Create multiple PDF files
        pdf_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(suffix=f'_{i}.pdf', delete=False) as tmp:
                tmp.write(sample_pdf_content)
                pdf_files.append(tmp.name)
        
        try:
            # Upload all files
            task_ids = []
            for pdf_path in pdf_files:
                with open(pdf_path, 'rb') as f:
                    files = {'files': (os.path.basename(pdf_path), f, 'application/pdf')}
                    response = httpx.post(f"{NGINX_URL}/upload/upload", files=files)
                
                assert response.status_code == 200
                upload_data = response.json()
                task_ids.append(upload_data["results"][0]["task_id"])
            
            # Check all tasks
            response = httpx.get(f"{MASTER_TASK_DB_URL}/tasks")
            assert response.status_code == 200
            all_tasks = response.json()
            
            # Verify our tasks are in the list
            task_ids_in_system = [task["id"] for task in all_tasks]
            for task_id in task_ids:
                assert task_id in task_ids_in_system
            
        finally:
            for pdf_path in pdf_files:
                os.unlink(pdf_path)

    def test_07_error_handling(self):
        """Test error handling for invalid requests"""
        
        # Test invalid file upload (non-PDF)
        files = {'files': ('test.txt', b'Not a PDF', 'text/plain')}
        response = httpx.post(f"{NGINX_URL}/upload/upload", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "error"
        assert "Only PDF files are allowed" in data["results"][0]["message"]
        
        # Test invalid chunk configuration
        invalid_config = {
            "chunk_size": 50,  # Too small
            "overlap_percentage": 2.0  # Too large
        }
        response = httpx.put(f"{NGINX_URL}/chunk-config/config", json=invalid_config)
        assert response.status_code == 422
        
        # Test querying non-existent task
        response = httpx.get(f"{MASTER_TASK_DB_URL}/tasks/non-existent-task")
        assert response.status_code == 404