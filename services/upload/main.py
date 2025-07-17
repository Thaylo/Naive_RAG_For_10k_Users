from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import aiofiles
import httpx
import os
from typing import List
import uuid
from datetime import datetime

from shared.models.task import TaskStatus
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error

# Setup logger
logger = setup_logger("upload-service", os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="Upload Service")

UPLOAD_DIR = "/app/storage/uploads"
MASTER_TASK_DB_URL = os.getenv("MASTER_TASK_DB_URL", "http://master-task-db:8001")


@app.on_event("startup")
async def startup_event():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    logger.info(f"Upload service started. Upload directory: {UPLOAD_DIR}")
    logger.info(f"Master Task DB URL: {MASTER_TASK_DB_URL}")


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    log_request(logger, "POST", "/upload", file_count=len(files))
    
    if not files:
        logger.warning("No files provided in upload request")
        raise HTTPException(status_code=400, detail="No files provided")
    
    results = []
    
    async with httpx.AsyncClient() as client:
        for file in files:
            logger.info(f"Processing file: {file.filename}, size: {file.size if hasattr(file, 'size') else 'unknown'}")
            
            if not file.filename.endswith('.pdf'):
                logger.warning(f"Rejected non-PDF file: {file.filename}")
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "message": "Only PDF files are allowed"
                })
                continue
            
            try:
                # Save file
                file_id = str(uuid.uuid4())
                file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
                
                logger.info(f"Saving file to: {file_path}")
                content = await file.read()
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(content)
                logger.info(f"File saved successfully: {file_path}, size: {len(content)} bytes")
                
                # Create task
                logger.info(f"Creating task for file: {file.filename}")
                response = await client.post(
                    f"{MASTER_TASK_DB_URL}/tasks/",
                    params={"filename": file.filename}
                )
                logger.info(f"Task creation response: status={response.status_code}")
                
                if response.status_code == 200:
                    task = response.json()
                    task_id = task["id"]
                    logger.info(f"Task created successfully: {task_id} for {file.filename}")
                    
                    # Save metadata
                    metadata_path = os.path.join(UPLOAD_DIR, f"{task_id}.metadata")
                    logger.debug(f"Writing metadata to: {metadata_path}")
                    async with aiofiles.open(metadata_path, 'w') as f:
                        await f.write(file_path)
                    logger.debug(f"Metadata written successfully")
                    
                    # Update task status
                    logger.info(f"Updating task status to UPLOAD_COMPLETED for task: {task_id}")
                    status_response = await client.put(
                        f"{MASTER_TASK_DB_URL}/tasks/{task_id}/status",
                        params={"status": TaskStatus.UPLOAD_COMPLETED.value}
                    )
                    logger.info(f"Status update response: {status_response.status_code}")
                    
                    if status_response.status_code != 200:
                        logger.error(f"Failed to update task status: {status_response.text}")
                        # Still mark as success since file was uploaded
                    
                    results.append({
                        "filename": file.filename,
                        "status": "success",
                        "task_id": task_id,
                        "message": "File uploaded successfully"
                    })
                    logger.info(f"Upload completed successfully for {file.filename}")
                else:
                    logger.error(f"Failed to create task for {file.filename}: {response.text}")
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "message": "Failed to create task"
                    })
                    
            except Exception as e:
                log_error(logger, e, f"upload_files for {file.filename}")
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "message": str(e)
                })
    
    log_response(logger, "POST", "/upload", 200, results_count=len(results))
    return JSONResponse(content={"results": results})


@app.get("/file/{task_id}")
async def get_file_path(task_id: str):
    log_request(logger, "GET", f"/file/{task_id}")
    
    metadata_path = os.path.join(UPLOAD_DIR, f"{task_id}.metadata")
    
    if not os.path.exists(metadata_path):
        logger.warning(f"Metadata file not found for task: {task_id}")
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        async with aiofiles.open(metadata_path, 'r') as f:
            file_path = await f.read()
        
        logger.info(f"Retrieved file path for task {task_id}: {file_path}")
        log_response(logger, "GET", f"/file/{task_id}", 200)
        return {"task_id": task_id, "file_path": file_path}
    except Exception as e:
        log_error(logger, e, f"get_file_path for task {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "upload"}