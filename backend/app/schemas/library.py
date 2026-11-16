from pydantic import BaseModel
from typing import Optional, List
import datetime

class LibraryAssetCreate(BaseModel):
    category: str
    title: str

class LibraryAssetResponse(BaseModel):
    id: str
    category: str
    title: str
    filename: str
    duration_seconds: float
    format: str
    file_size_bytes: int
    is_active: bool
    version: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class LibraryAssetListResponse(BaseModel):
    category: str
    assets: List[LibraryAssetResponse]
