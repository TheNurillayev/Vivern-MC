import asyncio
import tempfile
import os
from backend.app.services.speech import get_speech_recognizer
from backend.app.services.speech.base import SpeechSegment
from backend.app.services.analysis import get_conversation_analyzer
from backend.tests.test_phase1_admin_library import generate_test_wav

def test_uzbek_transcription_at_06():
    """AT-06: Uzbek speech recognition returns timestamped transcript segments."""
    recognizer = get_speech_recognizer()

    # Generate a sample audio file
    wav_bytes = generate_test_wav(duration_seconds=12.0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    try:
        result = asyncio.run(recognizer.transcribe(tmp_path, language="uz"))
        assert result.language == "uz"
        assert len(result.segments) >= 2, "Expected multiple timestamped speech segments"
        assert result.duration_seconds >= 11.9

        for seg in result.segments:
            assert seg.start_seconds < seg.end_seconds
            assert len(seg.text) > 0

        # Check that transcript includes conversational text
        assert "muborak" in result.full_text.lower() or "salom" in result.full_text.lower()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_stage_detection_high_confidence_at_07():
    """AT-07: Stage detection classifies wishes and call ending with high confidence on clear speech."""
    analyzer = get_conversation_analyzer()

    segments = [
        SpeechSegment(start_seconds=1.0, end_seconds=8.0, text="Assalomu alaykum! Ishlar yaxshimi?"),
        SpeechSegment(start_seconds=8.5, end_seconds=22.0, text="Bugun tug'ilgan kuningiz bilan chin qalbimdan tabriklayman! Sog'lik va omad tilayman!"),
        SpeechSegment(start_seconds=22.5, end_seconds=30.0, text="Katta rahmat! Mayli, yaxshi yetib oling, xayr!")
    ]

    analysis = asyncio.run(analyzer.analyze_stages(segments, total_duration=30.0))

    assert analysis.wishes_start_seconds == 8.5
    assert analysis.call_ending_start_seconds == 22.5
    assert analysis.wishes_confidence >= 0.85
    assert analysis.call_ending_confidence >= 0.85
    assert analysis.overall_confidence >= 0.85
    assert len(analysis.warnings) == 0

def test_stage_detection_uncertainty_flagging():
    """AT-07 fallback: Low-confidence/unclear sections flagged with warnings."""
    analyzer = get_conversation_analyzer()

    # Ambiguous segments missing explicit birthday wishes keywords
    segments = [
        SpeechSegment(start_seconds=0.5, end_seconds=5.0, text="Alo, eshityapsizmi?"),
        SpeechSegment(start_seconds=5.5, end_seconds=15.0, text="Ertaga bozorga boramizmi, nima deysiz?")
    ]

    analysis = asyncio.run(analyzer.analyze_stages(segments, total_duration=15.0))

    # Low confidence must be flagged and warning generated
    assert analysis.overall_confidence < 0.65
    assert len(analysis.warnings) > 0
    assert any("tilak" in w.lower() or "topilmadi" in w.lower() for w in analysis.warnings)

if __name__ == "__main__":
    print("Running Phase 3 acceptance tests (AT-06, AT-07)...")
    test_uzbek_transcription_at_06()
    print("PASS: AT-06 Uzbek timestamped transcription")

    test_stage_detection_high_confidence_at_07()
    print("PASS: AT-07 Stage detection (Wishes & Ending sections identified)")

    test_stage_detection_uncertainty_flagging()
    print("PASS: AT-07 Low-confidence and ambiguous transitions flagged")

    print("\nALL PHASE 3 ACCEPTANCE TESTS PASSED!")
