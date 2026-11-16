from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pydantic import BaseModel

class SpeechSegment(BaseModel):
    start_seconds: float
    end_seconds: float
    text: str

class SpeechTranscriptionResult(BaseModel):
    language: str
    full_text: str
    segments: List[SpeechSegment]
    duration_seconds: float

class BaseSpeechRecognizer(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str, language: str = "uz") -> SpeechTranscriptionResult:
        """Transcribe audio into timestamped segments."""
        pass
