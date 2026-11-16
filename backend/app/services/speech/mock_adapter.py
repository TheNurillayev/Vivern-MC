import math
from backend.app.services.speech.base import BaseSpeechRecognizer, SpeechTranscriptionResult, SpeechSegment
from backend.app.services.audio.validator import validate_audio_file

class MockSpeechRecognizer(BaseSpeechRecognizer):
    """
    Mock/Development adapter that provides realistic Uzbek birthday conversation
    transcripts with proportional timestamps based on the audio duration.
    """
    async def transcribe(self, audio_path: str, language: str = "uz") -> SpeechTranscriptionResult:
        meta = validate_audio_file(audio_path)
        total_dur = meta["duration_seconds"]

        # Realistic Uzbek birthday conversation stages:
        # 1. Opening greeting (first 25%)
        # 2. Birthday wishes (25% to 75%)
        # 3. Call ending (last 25%)
        t_start = round(total_dur * 0.05, 1)
        t_greet_end = round(total_dur * 0.25, 1)
        t_wishes_start = round(total_dur * 0.28, 1)
        t_wishes_end = round(total_dur * 0.72, 1)
        t_ending_start = round(total_dur * 0.75, 1)
        t_call_end = round(total_dur * 0.95, 1)

        segments = [
            SpeechSegment(
                start_seconds=t_start,
                end_seconds=t_greet_end,
                text="Alo, assalomu alaykum! Yaxshimisiz, charchamay yuribsizmi?"
            ),
            SpeechSegment(
                start_seconds=t_wishes_start,
                end_seconds=t_wishes_end,
                text="Bugungi tavallud ayyomingiz, tug'ilgan kuningiz muborak bo'lsin! Sizga uzoq umr, mustahkam sog'lik va bitmas-tuganmas baxt tilayman!"
            ),
            SpeechSegment(
                start_seconds=t_ending_start,
                end_seconds=t_call_end,
                text="Katta rahmat, sog' bo'ling, mayli ko'rishguncha, xayr!"
            )
        ]

        full_text = " ".join(s.text for s in segments)

        return SpeechTranscriptionResult(
            language=language,
            full_text=full_text,
            segments=segments,
            duration_seconds=total_dur
        )
