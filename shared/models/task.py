from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    UPLOAD_PENDING = "upload_pending"
    UPLOAD_COMPLETED = "upload_completed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    VECTORIZED = "vectorized"
    FAILED = "failed"


class Task(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    filename: str = Field(..., description="Name of the PDF file")
    status: TaskStatus = Field(default=TaskStatus.UPLOAD_PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    retry_count: int = Field(default=0)
    worker_id: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True