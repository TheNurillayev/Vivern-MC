import os
import asyncio
import logging
from typing import List
import httpx
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.services.audio.validator import validate_audio_file
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class GladiaSpeechRecognizer(BaseSpeechRecognizer):
    """
    High-accuracy speech recognition via Gladia API v2 (Whisper-powered).
    10 hours free per month, instant key, excellent Uzbek transcription.
    """
    def __init__(self):
        self.api_key = getattr(settings, "GLADIA_API_KEY", "") or os.getenv("GLADIA_API_KEY", "")
        self.fallback = MockSpeechRecognizer()

    async def transcribe(self, audio_path: str, language: str = "uz") -> SpeechTranscriptionResult:
        meta = validate_audio_file(audio_path)
        total_dur = meta["duration_seconds"]

        if not self.api_key:
            logger.info("GLADIA_API_KEY not configured, using fallback.")
            return await self.fallback.transcribe(audio_path, language=language)

        headers = {
            "x-gladia-key": self.api_key
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Step 1: Upload the audio file to Gladia
                logger.info(f"Uploading audio to Gladia for transcription: {audio_path}")
                upload_url = "https://api.gladia.io/v2/upload"
                with open(audio_path, "rb") as f:
                    files = {"audio": (os.path.basename(audio_path), f, "audio/mpeg")}
                    up_res = await client.post(upload_url, headers=headers, files=files)

                if up_res.status_code not in (200, 201):
                    logger.error(f"Gladia upload failed ({up_res.status_code}): {up_res.text[:300]}")
                    return await self.fallback.transcribe(audio_path, language=language)

                audio_url = up_res.json().get("audio_url")
                if not audio_url:
                    logger.error("Gladia did not return audio_url.")
                    return await self.fallback.transcribe(audio_path, language=language)

                # Step 2: Request transcription
                pre_recorded_url = "https://api.gladia.io/v2/pre-recorded"
                payload = {
                    "audio_url": audio_url,
                    "diarization": False
                }
                job_res = await client.post(pre_recorded_url, headers={**headers, "Content-Type": "application/json"}, json=payload)
                if job_res.status_code not in (200, 201):
                    logger.error(f"Gladia job creation failed: {job_res.text[:300]}")
                    return await self.fallback.transcribe(audio_path, language=language)

                result_url = job_res.json().get("result_url")
                if not result_url:
                    logger.error("Gladia did not return result_url.")
                    return await self.fallback.transcribe(audio_path, language=language)

                # Step 3: Poll for completion
                logger.info("Waiting for Gladia transcription to finish...")
                for _ in range(40):
                    await asyncio.sleep(2.5)
                    poll_res = await client.get(result_url, headers=headers)
                    if poll_res.status_code == 200:
                        res_json = poll_res.json()
                        status = res_json.get("status")
                        if status == "done":
                            result = res_json.get("result", {})
                            trans = result.get("transcription", {})
                            full_text = trans.get("full_transcript", "")
                            utterances = trans.get("utterances", [])

                            segments: List[SpeechSegment] = []
                            for u in utterances:
                                s_start = round(float(u.get("start", 0.0)), 2)
                                s_end = round(float(u.get("end", 0.0)), 2)
                                s_text = u.get("text", "").strip()
                                if s_text:
                                    segments.append(SpeechSegment(
                                        start_seconds=s_start,
                                        end_seconds=s_end,
                                        text=s_text
                                    ))

                            if not segments and full_text:
                                segments.append(SpeechSegment(
                                    start_seconds=0.0,
                                    end_seconds=total_dur,
                                    text=full_text
                                ))

                            logger.info(f"Gladia transcription completed: {len(segments)} segments recognized.")
                            return SpeechTranscriptionResult(
                                language=language,
                                full_text=full_text,
                                segments=segments,
                                duration_seconds=total_dur
                            )
                        elif status == "error":
                            logger.error(f"Gladia transcription error: {res_json}")
                            break

        except Exception as e:
            logger.error(f"Gladia transcription exception: {e}")

        return await self.fallback.transcribe(audio_path, language=language)
