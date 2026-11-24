import os
import json
import logging
from typing import List
from backend.app.services.speech.base import SpeechSegment
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult
from backend.app.services.analysis.heuristic_adapter import HeuristicConversationAnalyzer
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class OpenAIConversationAnalyzer(BaseConversationAnalyzer):
    """
    LLM-based conversation classifier (supports OpenAI and DeepSeek).
    Extracts wishes and ending section timestamps using structured JSON schema.
    Falls back to Heuristic analyzer when API keys are not configured.
    """
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY
        self.is_deepseek = bool(settings.DEEPSEEK_API_KEY and not settings.OPENAI_API_KEY)
        self.fallback = HeuristicConversationAnalyzer()

    async def analyze_stages(
        self,
        segments: List[SpeechSegment],
        total_duration: float
    ) -> StageAnalysisResult:
        if not self.api_key:
            logger.info("OpenAI or DeepSeek API key not set, using heuristic conversation analyzer.")
            return await self.fallback.analyze_stages(segments, total_duration)

        try:
            import httpx

            # Clean segments for LLM (filter noise / empty segments)
            cleaned_segments = []
            for s in segments:
                t = s.text.strip()
                if t and len(t) > 1:
                    cleaned_segments.append({"start": s.start_seconds, "end": s.end_seconds, "text": t})

            system_prompt = (
                "You are an expert audio mastering director analyzing the semantic meaning, speech acts, and conversational tone of Uzbek birthday phone calls.\n\n"
                "Calls have 3 distinct musical phases:\n"
                "1. INTERACTIVE CHIT-CHAT (Starter BG): Host and recipient chatting back-and-forth, teasing, asking who called, getting ready.\n"
                "   CRITICAL: Casual polite pleasantries like 'tabriklaymiz', 'sog'lik tilayman', or 'omon bo'ling' during early banter are NOT the dedicated wish monologue!\n"
                "2. DEDICATION MONOLOGUE (Wishes BG - wishes_start_seconds):\n"
                "   The speech act shifts from 2-way dialogue to a 1-way literary/emotional reading of a letter, poem, or heartfelt message dedicated to the recipient.\n"
                "   TIMING RULES FOR wishes_start_seconds:\n"
                "   - If the host says a transitional cue (e.g. 'Unday bo'lsa quloq tuting', 'Sizga atalgan maxsus tabrikni o'qib beramiz', 'Hozir sizga xatni o'qiyman'), 'wishes_start_seconds' MUST be set to the EXACT timestamp where the actual poetic reading or formal dedication begins (e.g., 'Avvalambor...', or the first line of the poem/letter), NOT during the transitional chatter.\n"
                "   - It does NOT require formulaic greetings like 'avvalambor' — detect it by the register shift into poetic, personal, emotionally intense dedication addressed to or honoring the recipient.\n"
                "3. CALL ENDING BG (call_ending_start_seconds):\n"
                "   The Wishes BG concludes and Call Ending BG starts at the EXACT MOMENT the final line/rhyme of the poem or personal letter concludes!\n"
                "   CRITICAL TIMING RULES FOR call_ending_start_seconds:\n"
                "   - Identify the exact segment where the poem or letter's last line ends (e.g. 'Baxtim uchun har nega tayyordir akam', 'Umringiz ziyoda bo'lsin').\n"
                "   - If followed by an attribution tag (e.g. 'Deya...', 'Deb tilab qoladilar...', 'Mana shunday ezgu tilaklarni akangiz yubordilar'), set 'call_ending_start_seconds' to the end of the poem line or the start of 'Deya/Deb/Mana shunday'.\n"
                "   - If the host immediately asks a reaction question (e.g. 'Qanday bo'ldi?', 'Yoqdimi?', 'Kim deb o'ylaysiz?'), set 'call_ending_start_seconds' to the exact end of the poem before the question.\n"
                "   - NEVER extend Wishes BG into the post-poem reaction discussion or farewell.\n\n"
                "Return ONLY valid JSON with keys:\n"
                "- wishes_start_seconds: (float) exact timestamp where the dedication reading begins\n"
                "- call_ending_start_seconds: (float) exact timestamp where the dedication reading finishes and wrap-up begins\n"
                "- wishes_confidence: (float 0.0-1.0)\n"
                "- call_ending_confidence: (float 0.0-1.0)\n"
                "- reasoning: (string) brief explanation of the chosen boundaries\n"
                "- warnings: (list of strings)"
            )

            user_prompt = (
                f"Total audio duration: {total_duration} seconds.\n"
                f"Timestamped transcript segments:\n{cleaned_segments}"
            )

            api_url = "https://api.deepseek.com/chat/completions" if self.is_deepseek else "https://api.openai.com/v1/chat/completions"
            model_name = "deepseek-chat" if self.is_deepseek else "gpt-4o-mini"

            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    content = json.loads(data["choices"][0]["message"]["content"])
                    w_start = float(content.get("wishes_start_seconds", total_duration * 0.3))
                    e_start = float(content.get("call_ending_start_seconds", total_duration * 0.75))
                    w_conf = float(content.get("wishes_confidence", 0.95))
                    e_conf = float(content.get("call_ending_confidence", 0.90))

                    # Snap to nearest speech segment boundary for sample-accurate crossfade
                    if segments:
                        best_w = w_start
                        min_diff_w = 999.0
                        for s in segments:
                            diff = abs(s.start_seconds - w_start)
                            if diff < min_diff_w and diff <= 1.8:
                                min_diff_w = diff
                                best_w = s.start_seconds

                        best_e = e_start
                        min_diff_e = 999.0
                        for s in segments:
                            diff = abs(s.end_seconds - e_start)
                            if diff < min_diff_e and diff <= 1.8:
                                min_diff_e = diff
                                best_e = s.end_seconds

                        w_start = best_w
                        e_start = max(w_start + 10.0, best_e)

                    reasoning = content.get("reasoning", "")
                    if reasoning:
                        logger.info(f"AI Stage Analysis Reasoning: {reasoning}")
                    warnings = content.get("warnings", [])
                    overall = round((w_conf + e_conf) / 2.0, 2)

                    return StageAnalysisResult(
                        language="uz",
                        wishes_start_seconds=w_start,
                        call_ending_start_seconds=e_start,
                        wishes_confidence=w_conf,
                        call_ending_confidence=e_conf,
                        overall_confidence=overall,
                        warnings=warnings,
                        transcript_segments=[{"start": s.start_seconds, "end": s.end_seconds, "text": s.text} for s in segments]
                    )
        except Exception as e:
            logger.error(f"LLM stage analysis call failed: {e}, using heuristic fallback.")

        return await self.fallback.analyze_stages(segments, total_duration)
