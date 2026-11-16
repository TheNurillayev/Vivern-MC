import os
import json
import logging
from typing import List
from backend.app.services.speech.base import SpeechSegment
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult
from backend.app.services.analysis.heuristic_adapter import HeuristicConversationAnalyzer
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class OpenAIConversationAnalyzer(BaseConversationAnalyzer):
    """
    OpenAI-based conversation classifier.
    Extracts wishes and ending section timestamps using structured JSON schema.
    Falls back to Heuristic analyzer when API key is not configured.
    """
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.fallback = HeuristicConversationAnalyzer()

    async def analyze_stages(
        self,
        segments: List[SpeechSegment],
        total_duration: float
    ) -> StageAnalysisResult:
        if not self.api_key:
            logger.info("OpenAI API key not set, using heuristic conversation analyzer.")
            return await self.fallback.analyze_stages(segments, total_duration)

        try:
            # When OpenAI API key is provided, we can call OpenAI API via requests/httpx
            import httpx
            prompt = (
                "You are an audio production assistant for Uzbek birthday phone call recordings.\n"
                "Analyze the timestamped transcript and identify the exact seconds where:\n"
                "1. The birthday wishes section begins (wishes_start_seconds)\n"
                "2. The call ending/farewell section begins (call_ending_start_seconds)\n"
                "Return only JSON with keys: wishes_start_seconds (float), call_ending_start_seconds (float), "
                "wishes_confidence (0.0-1.0), call_ending_confidence (0.0-1.0), warnings (list of strings).\n\n"
                f"Total duration: {total_duration} seconds.\n"
                f"Transcript segments: {[s.model_dump() for s in segments]}"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    content = json.loads(data["choices"][0]["message"]["content"])
                    w_start = float(content.get("wishes_start_seconds", total_duration * 0.3))
                    e_start = float(content.get("call_ending_start_seconds", total_duration * 0.75))
                    w_conf = float(content.get("wishes_confidence", 0.9))
                    e_conf = float(content.get("call_ending_confidence", 0.9))
                    warnings = content.get("warnings", [])
                    overall = round((w_conf + e_conf) / 2.0, 2)

                    return StageAnalysisResult(
                        language="uz",
                        wishes_start_seconds=w_start,
                        call_ending_start_seconds=e_start,
                        wishes_confidence=w_conf,
                        call_ending_confidence=e_conf,
                        overall_confidence=overall,
                        warnings=warnings,
                        transcript_segments=[{"start": s.start_seconds, "end": s.end_seconds, "text": s.text} for s in segments]
                    )
        except Exception as e:
            logger.error(f"OpenAI analysis call failed: {e}, using heuristic fallback.")

        return await self.fallback.analyze_stages(segments, total_duration)
