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
    LLM-based conversation classifier (supports OpenAI and DeepSeek).
    Extracts wishes and ending section timestamps using structured JSON schema.
    Falls back to Heuristic analyzer when API keys are not configured.
    """
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY
        self.is_deepseek = bool(settings.DEEPSEEK_API_KEY and not settings.OPENAI_API_KEY)
        self.fallback = HeuristicConversationAnalyzer()

    async def analyze_stages(
        self,
        segments: List[SpeechSegment],
        total_duration: float
    ) -> StageAnalysisResult:
        if not self.api_key:
            logger.info("OpenAI or DeepSeek API key not set, using heuristic conversation analyzer.")
            return await self.fallback.analyze_stages(segments, total_duration)

        try:
            import httpx

            # Clean segments for LLM (filter noise / empty segments)
            cleaned_segments = []
            for s in segments:
                t = s.text.strip()
                if t and len(t) > 1:
                    cleaned_segments.append({"start": s.start_seconds, "end": s.end_seconds, "text": t})

            prompt = (
                "You are a studio audio mastering director for Uzbek birthday phone call recordings.\n"
                "We must place 3 background music tracks behind the call:\n"
                "1. STARTER BG: Plays during the opening conversation, greetings, playful guessing game, and preamble.\n"
                "2. WISHES BG (wishes_start_seconds): Starts when the host begins reading the formal birthday wish / congratulatory letter / poem (e.g. 'Avvalambor assalomu alaykum, men uchun aziz bolgan akajonim...').\n"
                "3. CALL ENDING BG (call_ending_start_seconds): Starts when the birthday wish / poem reading FINISHES (e.g. 'Deya nomalarga yakun yasaymiz...', 'deb qolibdilar'), transitioning to the wrap-up discussion where the host asks how the recipient felt and begins final remarks.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "- Do NOT pick early casual greetings (e.g. before 1-2 minutes) as wishes_start_seconds!\n"
                "- 'call_ending_start_seconds' is the exact moment the wish/poem reading ends, NOT the end of the entire phone call.\n\n"
                f"Total duration: {total_duration} seconds.\n"
                f"Transcript segments: {cleaned_segments}\n\n"
                "Return ONLY valid JSON with keys: wishes_start_seconds (float), call_ending_start_seconds (float), "
                "wishes_confidence (0.0-1.0), call_ending_confidence (0.0-1.0), warnings (list of strings)."
            )

            api_url = "https://api.deepseek.com/chat/completions" if self.is_deepseek else "https://api.openai.com/v1/chat/completions"
            model_name = "deepseek-chat" if self.is_deepseek else "gpt-4o-mini"

            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    content = json.loads(data["choices"][0]["message"]["content"])
                    w_start = float(content.get("wishes_start_seconds", total_duration * 0.3))
                    e_start = float(content.get("call_ending_start_seconds", total_duration * 0.75))
                    w_conf = float(content.get("wishes_confidence", 0.95))
                    e_conf = float(content.get("call_ending_confidence", 0.90))
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
            logger.error(f"LLM stage analysis call failed: {e}, using heuristic fallback.")

        return await self.fallback.analyze_stages(segments, total_duration)
