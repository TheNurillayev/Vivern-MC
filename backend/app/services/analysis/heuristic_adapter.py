import logging
from typing import List, Dict, Any
from backend.app.services.speech.base import SpeechSegment
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult

logger = logging.getLogger(__name__)

PRIMARY_WISHES_MARKERS = [
    "avvalambor", "avvalam bor", "ruxsatingiz bilan", "dil izhor", 
    "nomadan yetib", "o'qib eshittir", "oqib eshittir", "tabriknoma"
]

GENERAL_WISHES_KEYWORDS = [
    "tug'ilgan kun", "muborak", "tabriklay", "qutlay", "tilayman", 
    "tilaymiz", "yosh", "baxt", "omad", "umr", "tavallud"
]

ENDING_POEM_MARKERS = [
    "deya", "diye", "deb qolibdilar", "deb qolamiz", "deb niyat", 
    "deb tilab", "nomalarga yakun", "yakun yasay", "yakuniga yet", 
    "she'rimiz", "aytmoqchi bo'lgan"
]

ENDING_FAREWELL_KEYWORDS = [
    "salomat bo'ling", "sog' bo'ling", "xayr", "mayli", "ko'rishguncha", 
    "yaxshi qoling", "omon bo'ling", "minnatdormiz"
]

class HeuristicConversationAnalyzer(BaseConversationAnalyzer):
    """
    Analyzes Uzbek transcript segments using conversation keyword detection
    and temporal positioning to detect transition points.
    Distinguishes casual introductory banter from the formal wish/letter reading.
    """
    async def analyze_stages(
        self,
        segments: List[SpeechSegment],
        total_duration: float
    ) -> StageAnalysisResult:
        warnings = []
        segments_dict = [
            {"start": s.start_seconds, "end": s.end_seconds, "text": s.text}
            for s in segments
        ]

        if not segments or total_duration <= 0:
            return StageAnalysisResult(
                wishes_start_seconds=round(total_duration * 0.3, 1),
                call_ending_start_seconds=round(total_duration * 0.75, 1),
                wishes_confidence=0.3,
                call_ending_confidence=0.3,
                overall_confidence=0.3,
                warnings=["Ovoz yozuvi yoki matn segmentlari topilmadi."],
                transcript_segments=segments_dict
            )

        wishes_idx = None
        ending_idx = None

        # Introductory banter in birthday radio calls usually lasts at least 30-45s
        min_wishes_time = 35.0 if total_duration > 90.0 else 5.0

        # Phase 1: Search for primary wish markers after introductory banter
        for i, seg in enumerate(segments):
            if seg.start_seconds < min_wishes_time:
                continue
            text_lower = seg.text.lower()
            if any(k in text_lower for k in PRIMARY_WISHES_MARKERS):
                wishes_idx = i
                break

        # Phase 2: If not found, search general wishes keywords after min_wishes_time
        if wishes_idx is None:
            for i, seg in enumerate(segments):
                if seg.start_seconds < min_wishes_time:
                    continue
                text_lower = seg.text.lower()
                if any(k in text_lower for k in GENERAL_WISHES_KEYWORDS):
                    wishes_idx = i
                    break

        # Phase 3: Fallback for very short recordings
        if wishes_idx is None:
            for i, seg in enumerate(segments):
                text_lower = seg.text.lower()
                if any(k in text_lower for k in PRIMARY_WISHES_MARKERS + GENERAL_WISHES_KEYWORDS):
                    wishes_idx = i
                    break

        wishes_confidence = 0.95 if wishes_idx is not None else 0.45
        if wishes_idx is not None:
            wishes_start = segments[wishes_idx].start_seconds
        else:
            wishes_start = round(total_duration * 0.30, 1)
            warnings.append("Tug'ilgan kun tilaklari qismi aniq topilmadi, standart oraliq tavsiya etildi.")

        # Phase 4: Search forward for wish conclusion / poem end (at least 25s after wishes_start)
        min_ending_time = wishes_start + 25.0
        if wishes_idx is not None:
            for i in range(wishes_idx + 1, len(segments)):
                if segments[i].start_seconds < min_ending_time:
                    continue
                text_lower = segments[i].text.lower()
                if any(k in text_lower for k in ENDING_POEM_MARKERS):
                    ending_idx = i
                    break

        ending_confidence = 0.90 if ending_idx is not None else 0.45
        if ending_idx is not None:
            ending_start = segments[ending_idx].start_seconds
        else:
            # If explicit poem end marker not found, check for wrap-up discussion transition
            ending_start = round(min(total_duration - 10.0, max(wishes_start + 45.0, total_duration * 0.70)), 1)
            warnings.append("Tilak yakuni belgisi topilmadi, umumiy oraliq tavsiya etildi.")

        # Sanity checks
        if wishes_start >= ending_start:
            wishes_start = round(total_duration * 0.25, 1)
            ending_start = round(total_duration * 0.75, 1)
            wishes_confidence = min(wishes_confidence, 0.4)
            ending_confidence = min(ending_confidence, 0.4)
            warnings.append("Tilak va yakun vaqtlari o'zaro mos kelmadi, qayta ko'rib chiqish talab etiladi.")

        overall_confidence = round((wishes_confidence + ending_confidence) / 2.0, 2)

        return StageAnalysisResult(
            language="uz",
            wishes_start_seconds=round(wishes_start, 2),
            call_ending_start_seconds=round(ending_start, 2),
            wishes_confidence=round(wishes_confidence, 2),
            call_ending_confidence=round(ending_confidence, 2),
            overall_confidence=overall_confidence,
            warnings=warnings,
            transcript_segments=segments_dict
        )
