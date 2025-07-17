from pydantic import BaseModel, Field
from typing import Optional, List


class ChunkConfig(BaseModel):
    chunk_size: int = Field(default=1000, ge=100, le=5000)
    overlap_percentage: float = Field(default=0.1, ge=0.0, le=0.5)
    strategy: str = Field(default="fixed_size")


class Chunk(BaseModel):
    id: str = Field(..., description="Unique chunk identifier")
    task_id: str = Field(..., description="Parent task ID")
    content: str = Field(..., description="Text content of the chunk")
    chunk_index: int = Field(..., description="Position of chunk in document")
    start_char: int = Field(..., description="Starting character position in original document")
    end_char: int = Field(..., description="Ending character position in original document")
    metadata: dict = Field(default_factory=dict)