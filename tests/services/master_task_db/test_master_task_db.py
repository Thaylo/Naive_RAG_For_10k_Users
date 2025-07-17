import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import asyncio

from services.master_task_db.main import app, task_db, TaskDatabase
from shared.models.task import Task, TaskStatus


@pytest.fixture
def client():
    task_db.tasks.clear()
    return TestClient(app)


@pytest.fixture
def sample_task():
    return {
        "filename": "test_document.pdf"
    }


class TestTaskDatabase:
    @pytest.mark.asyncio
    async def test_create_task(self):
        db = TaskDatabase()
        task = await db.create_task("test.pdf")
        
        assert task.filename == "test.pdf"
        assert task.status == TaskStatus.UPLOAD_PENDING
        assert task.id in db.tasks
    
    @pytest.mark.asyncio
    async def test_get_task(self):
        db = TaskDatabase()
        created_task = await db.create_task("test.pdf")
        
        task = await db.get_task(created_task.id)
        assert task is not None
        assert task.id == created_task.id
        
        task = await db.get_task("non-existent")
        assert task is None
    
    @pytest.mark.asyncio
    async def test_update_task_status(self):
        db = TaskDatabase()
        task = await db.create_task("test.pdf")
        
        updated_task = await db.update_task_status(
            task.id, 
            TaskStatus.CHUNKING, 
            "worker-123"
        )
        
        assert updated_task.status == TaskStatus.CHUNKING
        assert updated_task.worker_id == "worker-123"
        
        with pytest.raises(ValueError):
            await db.update_task_status("non-existent", TaskStatus.CHUNKING)
    
    @pytest.mark.asyncio
    async def test_update_heartbeat(self):
        db = TaskDatabase()
        task = await db.create_task("test.pdf")
        await db.update_task_status(task.id, TaskStatus.CHUNKING, "worker-123")
        
        success = await db.update_heartbeat(task.id, "worker-123")
        assert success is True
        assert db.tasks[task.id].last_heartbeat is not None
        
        success = await db.update_heartbeat(task.id, "wrong-worker")
        assert success is False
    
    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self):
        db = TaskDatabase()
        
        task1 = await db.create_task("test1.pdf")
        task2 = await db.create_task("test2.pdf")
        await db.update_task_status(task2.id, TaskStatus.CHUNKING)
        
        pending_tasks = await db.get_tasks_by_status(TaskStatus.UPLOAD_PENDING)
        assert len(pending_tasks) == 1
        assert pending_tasks[0].id == task1.id
        
        chunking_tasks = await db.get_tasks_by_status(TaskStatus.CHUNKING)
        assert len(chunking_tasks) == 1
        assert chunking_tasks[0].id == task2.id
    
    @pytest.mark.asyncio
    async def test_check_dead_tasks(self):
        db = TaskDatabase()
        db.heartbeat_timeout = timedelta(seconds=1)
        
        task = await db.create_task("test.pdf")
        await db.update_task_status(task.id, TaskStatus.CHUNKING, "worker-123")
        
        db.tasks[task.id].last_heartbeat = datetime.utcnow() - timedelta(seconds=2)
        
        await db.check_dead_tasks()
        
        updated_task = db.tasks[task.id]
        assert updated_task.status == TaskStatus.UPLOAD_COMPLETED
        assert updated_task.worker_id is None
        assert updated_task.retry_count == 1


class TestAPI:
    def test_create_task_endpoint(self, client):
        response = client.post("/tasks/?filename=test.pdf")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.pdf"
        assert data["status"] == "upload_pending"
        assert "id" in data
    
    def test_get_task_endpoint(self, client):
        create_response = client.post("/tasks/?filename=test.pdf")
        task_id = create_response.json()["id"]
        
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["filename"] == "test.pdf"
        
        response = client.get("/tasks/non-existent")
        assert response.status_code == 404
    
    def test_update_task_status_endpoint(self, client):
        create_response = client.post("/tasks/?filename=test.pdf")
        task_id = create_response.json()["id"]
        
        response = client.put(
            f"/tasks/{task_id}/status?status=chunking&worker_id=worker-123"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "chunking"
        assert data["worker_id"] == "worker-123"
        
        response = client.put("/tasks/non-existent/status?status=chunking")
        assert response.status_code == 404
    
    def test_heartbeat_endpoint(self, client):
        create_response = client.post("/tasks/?filename=test.pdf")
        task_id = create_response.json()["id"]
        
        client.put(f"/tasks/{task_id}/status?status=chunking&worker_id=worker-123")
        
        response = client.post(
            f"/tasks/{task_id}/heartbeat?worker_id=worker-123"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        response = client.post(
            f"/tasks/{task_id}/heartbeat?worker_id=wrong-worker"
        )
        assert response.status_code == 403
    
    def test_get_tasks_by_status_endpoint(self, client):
        client.post("/tasks/?filename=test1.pdf")
        client.post("/tasks/?filename=test2.pdf")
        
        response = client.get("/tasks/status/upload_pending")
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 2
        assert all(task["status"] == "upload_pending" for task in tasks)
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "master_task_db"