from backend.app.core.config import settings
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.speech.mock_adapter import MockSpeechRecognizer
from backend.app.services.speech.google_adapter import GoogleSpeechRecognizer

def get_speech_recognizer() -> BaseSpeechRecognizer:
    if settings.SPEECH_PROVIDER == "google_chirp":
        return GoogleSpeechRecognizer()
    return MockSpeechRecognizer()

__all__ = ["get_speech_recognizer", "BaseSpeechRecognizer", "SpeechTranscriptionResult", "SpeechSegment"]
