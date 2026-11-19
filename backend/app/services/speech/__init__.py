import os
from backend.app.core.config import settings
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.services.speech.google_adapter import GoogleSpeechRecognizer
from backend.app.services.speech.whisper_adapter import WhisperSpeechRecognizer
from backend.app.services.speech.gladia_adapter import GladiaSpeechRecognizer

def get_speech_recognizer() -> BaseSpeechRecognizer:
    # 1. Groq or OpenAI Whisper if configured
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    openai_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if groq_key or openai_key or getattr(settings, "SPEECH_PROVIDER", "") in ("groq", "whisper"):
        return WhisperSpeechRecognizer()

    # 2. Gladia Whisper API if configured
    gladia_key = getattr(settings, "GLADIA_API_KEY", "") or os.getenv("GLADIA_API_KEY", "")
    if gladia_key or getattr(settings, "SPEECH_PROVIDER", "") == "gladia":
        return GladiaSpeechRecognizer()

    # 3. Google Chirp if credentials exist
    if getattr(settings, "SPEECH_PROVIDER", "") == "google_chirp":
        return GoogleSpeechRecognizer()

    return MockSpeechRecognizer()

__all__ = ["get_speech_recognizer", "BaseSpeechRecognizer", "SpeechTranscriptionResult", "SpeechSegment", "WhisperSpeechRecognizer", "GladiaSpeechRecognizer"]
