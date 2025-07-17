from pydantic import BaseModel, Field
from typing import List, Optional


class Embedding(BaseModel):
    id: str = Field(..., description="Unique embedding identifier")
    chunk_id: str = Field(..., description="Associated chunk ID")
    task_id: str = Field(..., description="Parent task ID")
    vector: List[float] = Field(..., description="Embedding vector")
    model_name: str = Field(default="mock-embedding-model")
    dimension: int = Field(default=384)