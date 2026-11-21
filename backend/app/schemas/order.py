import datetime
from typing import Optional, List
from pydantic import BaseModel

class OrderCreateResponse(BaseModel):
    id: str
    status: str
    audio_title: Optional[str] = ""
    original_recording_name: str
    special_music_name: str
    price_som: int
    is_free_trial: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class OrderDetailResponse(BaseModel):
    id: str
    status: str
    audio_title: Optional[str] = ""
    original_recording_name: str
    special_music_name: str
    output_audio_duration: float
    price_som: int
    is_free_trial: bool
    is_paid: bool
    delivered_to_telegram: bool
    error_message: Optional[str] = ""
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
