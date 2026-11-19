import logging
from typing import List, Dict, Any
from backend.app.services.speech.base import SpeechSegment
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult

logger = logging.getLogger(__name__)

WISHES_KEYWORDS = [
    "avvalambor", "avvalam bor", "tug'ilgan kun", "muborak", "tabriklay", 
    "qutlay", "tilayman", "tilaymiz", "yosh", "baxt", "omad", "umr", "sog'lik", 
    "tavallud", "ruxsatingiz bilan", "dil izhor", "niyat qilib"
]

ENDING_KEYWORDS = [
    "deb qolibdilar", "deb qolamiz", "deb niyat", "deb tilab", "rahmat", 
    "salomat bo'ling", "sog' bo'ling", "xayr", "mayli", "ko'rishguncha", 
    "gaplashamiz", "yaxshi qoling", "sog' bo'l"
]

class HeuristicConversationAnalyzer(BaseConversationAnalyzer):
    """
    Analyzes Uzbek transcript segments using conversation keyword detection
    and temporal positioning to detect transition points.
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

        # Search for wishes keyword
        for i, seg in enumerate(segments):
            text_lower = seg.text.lower()
            if any(k in text_lower for k in WISHES_KEYWORDS):
                wishes_idx = i
                break

        # Search for ending keyword (scanning backwards or after wishes)
        for i in range(len(segments) - 1, -1, -1):
            text_lower = segments[i].text.lower()
            if any(k in text_lower for k in ENDING_KEYWORDS):
                ending_idx = i
                break

        # Calculate timestamps and confidences
        wishes_confidence = 0.95 if wishes_idx is not None else 0.45
        ending_confidence = 0.90 if ending_idx is not None else 0.40

        if wishes_idx is not None:
            wishes_start = segments[wishes_idx].start_seconds
        else:
            wishes_start = round(total_duration * 0.30, 1)
            warnings.append("Tug'ilgan kun tilaklari qismi aniq topilmadi, standart oraliq tavsiya etildi.")

        if ending_idx is not None and (wishes_idx is None or ending_idx > wishes_idx):
            ending_start = segments[ending_idx].start_seconds
        else:
            ending_start = round(total_duration * 0.75, 1)
            warnings.append("Qo'ng'iroq yakunlash qismi aniq topilmadi, standart oraliq tavsiya etildi.")

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
