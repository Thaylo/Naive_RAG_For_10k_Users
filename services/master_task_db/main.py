from fastapi import FastAPI, HTTPException, BackgroundTasks
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import uuid
import os
from contextlib import asynccontextmanager

from shared.models.task import Task, TaskStatus
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class TaskDatabase:
    def __init__(self):
        self.logger = setup_logger("master-task-db", os.getenv("LOG_LEVEL", "INFO"))
        self.tasks: Dict[str, Task] = {}
        self.heartbeat_timeout = timedelta(seconds=30)
        self.logger.info("TaskDatabase initialized")
    
    async def create_task(self, filename: str) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(id=task_id, filename=filename)
        self.tasks[task_id] = task
        self.logger.info(f"Created task {task_id} for file: {filename}")
        return task
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)
    
    async def update_task_status(self, task_id: str, status: TaskStatus, worker_id: Optional[str] = None) -> Task:
        task = self.tasks.get(task_id)
        if not task:
            self.logger.error(f"Task {task_id} not found")
            raise ValueError(f"Task {task_id} not found")
        
        old_status = task.status
        task.status = status
        task.updated_at = datetime.utcnow()
        
        # Clear worker_id when setting to terminal statuses
        if status in [TaskStatus.UPLOAD_COMPLETED, TaskStatus.CHUNKED, TaskStatus.EMBEDDED, TaskStatus.VECTORIZED, TaskStatus.FAILED]:
            task.worker_id = None
            task.last_heartbeat = None
        elif worker_id:
            task.worker_id = worker_id
            
        self.logger.info(f"Task {task_id} status updated: {old_status.value} -> {status.value}" + (f" (worker: {worker_id})" if worker_id else ""))
        return task
    
    async def update_heartbeat(self, task_id: str, worker_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task or task.worker_id != worker_id:
            return False
        
        task.last_heartbeat = datetime.utcnow()
        return True
    
    async def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        return [task for task in self.tasks.values() if task.status == status]
    
    async def check_dead_tasks(self):
        current_time = datetime.utcnow()
        for task in self.tasks.values():
            if (task.worker_id and 
                task.last_heartbeat and 
                task.status not in [TaskStatus.UPLOAD_PENDING, TaskStatus.VECTORIZED, TaskStatus.FAILED] and
                current_time - task.last_heartbeat > self.heartbeat_timeout):
                
                self.logger.warning(f"Task {task.id} heartbeat timeout, worker {task.worker_id} presumed dead")
                task.worker_id = None
                task.last_heartbeat = None
                task.retry_count += 1
                
                if task.retry_count > 3:
                    task.status = TaskStatus.FAILED
                    task.error_message = "Max retries exceeded"
                    self.logger.error(f"Task {task.id} failed after {task.retry_count} retries")
                else:
                    old_status = task.status
                    if task.status == TaskStatus.CHUNKING:
                        task.status = TaskStatus.UPLOAD_COMPLETED
                    elif task.status == TaskStatus.EMBEDDING:
                        task.status = TaskStatus.CHUNKED
                    self.logger.info(f"Task {task.id} reset from {old_status.value} to {task.status.value} for retry #{task.retry_count}")


task_db = TaskDatabase()


async def heartbeat_monitor():
    while True:
        await task_db.check_dead_tasks()
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(heartbeat_monitor())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Master Task Database Service", lifespan=lifespan)


@app.get("/tasks/", response_model=List[Task])
async def get_all_tasks():
    log_request(task_db.logger, "GET", "/tasks/")
    tasks = list(task_db.tasks.values())
    log_response(task_db.logger, "GET", "/tasks/", 200, count=len(tasks))
    return tasks


@app.post("/tasks/", response_model=Task)
async def create_task(filename: str):
    log_request(task_db.logger, "POST", "/tasks/", filename=filename)
    task = await task_db.create_task(filename)
    log_response(task_db.logger, "POST", "/tasks/", 200, task_id=task.id)
    return task


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    log_request(task_db.logger, "GET", f"/tasks/{task_id}")
    task = await task_db.get_task(task_id)
    if not task:
        task_db.logger.warning(f"Task {task_id} not found")
        raise HTTPException(status_code=404, detail="Task not found")
    log_response(task_db.logger, "GET", f"/tasks/{task_id}", 200)
    return task


@app.put("/tasks/{task_id}/status")
async def update_task_status(task_id: str, status: TaskStatus, worker_id: Optional[str] = None):
    log_request(task_db.logger, "PUT", f"/tasks/{task_id}/status", status=status.value, worker_id=worker_id)
    try:
        task = await task_db.update_task_status(task_id, status, worker_id)
        log_response(task_db.logger, "PUT", f"/tasks/{task_id}/status", 200)
        return task
    except ValueError as e:
        log_error(task_db.logger, e, "update_task_status")
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/tasks/{task_id}/heartbeat")
async def heartbeat(task_id: str, worker_id: str):
    success = await task_db.update_heartbeat(task_id, worker_id)
    if not success:
        raise HTTPException(status_code=403, detail="Invalid worker or task")
    return {"status": "ok"}


@app.get("/tasks/status/{status}", response_model=List[Task])
async def get_tasks_by_status(status: TaskStatus):
    log_request(task_db.logger, "GET", f"/tasks/status/{status.value}")
    tasks = await task_db.get_tasks_by_status(status)
    log_response(task_db.logger, "GET", f"/tasks/status/{status.value}", 200, count=len(tasks))
    return tasks


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "master_task_db"}