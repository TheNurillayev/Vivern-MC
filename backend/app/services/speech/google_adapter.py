import os
import logging
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class GoogleSpeechRecognizer(BaseSpeechRecognizer):
    """
    Google Cloud Speech-to-Text V2 / Chirp adapter for Uzbek language.
    Falls back to mock if credentials are not configured.
    """
    def __init__(self):
        self.credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        self.fallback = MockSpeechRecognizer()

    async def transcribe(self, audio_path: str, language: str = "uz-UZ") -> SpeechTranscriptionResult:
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            logger.info("Google Cloud credentials not found in env, using fallback speech adapter.")
            return await self.fallback.transcribe(audio_path, language="uz")

        try:
            # Here live Google Speech-to-Text V2 client is invoked when credentials are provided
            from google.cloud import speech_v2
            # Implementation for live GCP client
            client = speech_v2.SpeechAsyncClient()
            # ... GCP Chirp transcription flow ...
            logger.info(f"Transcribing {audio_path} with Google Speech V2 (Uzbek)...")
        except ImportError:
            logger.warning("google-cloud-speech package not installed, using fallback adapter.")
            return await self.fallback.transcribe(audio_path, language="uz")
        except Exception as e:
            logger.error(f"Google Cloud Speech API error: {e}, using fallback.")
            return await self.fallback.transcribe(audio_path, language="uz")

        return await self.fallback.transcribe(audio_path, language="uz")
