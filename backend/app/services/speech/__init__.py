import os
from backend.app.core.config import settings
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.services.speech.google_adapter import GoogleSpeechRecognizer
from backend.app.services.speech.whisper_adapter import WhisperSpeechRecognizer

def get_speech_recognizer() -> BaseSpeechRecognizer:
    # Auto-detect Whisper if Groq or OpenAI key is configured
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    openai_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    
    if groq_key or openai_key or getattr(settings, "SPEECH_PROVIDER", "") in ("groq", "whisper"):
        return WhisperSpeechRecognizer()

    if getattr(settings, "SPEECH_PROVIDER", "") == "google_chirp":
        return GoogleSpeechRecognizer()

    return MockSpeechRecognizer()

__all__ = ["get_speech_recognizer", "BaseSpeechRecognizer", "SpeechTranscriptionResult", "SpeechSegment", "WhisperSpeechRecognizer"]
