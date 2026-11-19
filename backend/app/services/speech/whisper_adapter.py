import os
import json
import logging
from typing import List
import httpx
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.services.audio.validator import validate_audio_file
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class WhisperSpeechRecognizer(BaseSpeechRecognizer):
    """
    High-accuracy Uzbek speech recognition using Whisper Large v3 (Groq or OpenAI).
    Transcribes audio into timestamped word/sentence segments in seconds.
    Falls back to mock/heuristic if API keys are not provided.
    """
    def __init__(self):
        self.groq_api_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
        self.openai_api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        self.fallback = MockSpeechRecognizer()

    async def transcribe(self, audio_path: str, language: str = "uz") -> SpeechTranscriptionResult:
        meta = validate_audio_file(audio_path)
        total_dur = meta["duration_seconds"]

        # Choose provider: Groq (ultra-fast, free tier) > OpenAI
        api_key = self.groq_api_key or self.openai_api_key
        if not api_key:
            logger.info("Neither GROQ_API_KEY nor OPENAI_API_KEY found, using fallback speech adapter.")
            return await self.fallback.transcribe(audio_path, language=language)

        is_groq = bool(self.groq_api_key)
        api_url = "https://api.groq.com/openai/v1/audio/transcriptions" if is_groq else "https://api.openai.com/v1/audio/transcriptions"
        model_name = "whisper-large-v3-turbo" if is_groq else "whisper-1"

        logger.info(f"Transcribing audio with {model_name} ({'Groq' if is_groq else 'OpenAI'})...")

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                with open(audio_path, "rb") as af:
                    files = {
                        "file": (os.path.basename(audio_path), af, "audio/mpeg")
                    }
                    data = {
                        "model": model_name,
                        "language": language,
                        "response_format": "verbose_json",
                        "temperature": "0.0"
                    }
                    headers = {
                        "Authorization": f"Bearer {api_key}"
                    }

                    res = await client.post(api_url, files=files, data=data, headers=headers)

                if res.status_code != 200:
                    logger.error(f"Whisper API error ({res.status_code}): {res.text[:500]}")
                    return await self.fallback.transcribe(audio_path, language=language)

                resp_data = res.json()
                raw_segments = resp_data.get("segments", [])
                full_text = resp_data.get("text", "")

                segments: List[SpeechSegment] = []
                for s in raw_segments:
                    start_s = round(float(s.get("start", 0.0)), 2)
                    end_s = round(float(s.get("end", 0.0)), 2)
                    txt = s.get("text", "").strip()
                    if txt:
                        segments.append(SpeechSegment(
                            start_seconds=start_s,
                            end_seconds=end_s,
                            text=txt
                        ))

                if not segments and full_text:
                    segments.append(SpeechSegment(
                        start_seconds=0.0,
                        end_seconds=total_dur,
                        text=full_text
                    ))

                logger.info(f"Whisper transcription succeeded: {len(segments)} segments recognized.")
                return SpeechTranscriptionResult(
                    language=language,
                    full_text=full_text,
                    segments=segments,
                    duration_seconds=total_dur
                )

        except Exception as e:
            logger.error(f"Whisper transcription exception: {e}, falling back.")
            return await self.fallback.transcribe(audio_path, language=language)
