from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.app.services.speech.base import SpeechSegment

class StageAnalysisResult(BaseModel):
    language: str = "uz"
    wishes_start_seconds: float
    call_ending_start_seconds: float
    wishes_confidence: float = 1.0
    call_ending_confidence: float = 1.0
    overall_confidence: float = 1.0
    warnings: List[str] = []
    transcript_segments: List[Dict[str, Any]] = []

class BaseConversationAnalyzer(ABC):
    @abstractmethod
    async def analyze_stages(
        self,
        segments: List[SpeechSegment],
        total_duration: float
    ) -> StageAnalysisResult:
        """Classify stages and return structured transition timestamps and confidences."""
        pass
