from backend.app.core.config import settings
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult
from backend.app.services.analysis.heuristic_adapter import HeuristicConversationAnalyzer
from backend.app.services.analysis.openai_adapter import OpenAIConversationAnalyzer

def get_conversation_analyzer() -> BaseConversationAnalyzer:
    if (
        settings.ANALYSIS_PROVIDER in ["openai", "deepseek"]
        or bool(settings.DEEPSEEK_API_KEY)
        or bool(settings.OPENAI_API_KEY)
    ):
        return OpenAIConversationAnalyzer()
    return HeuristicConversationAnalyzer()

__all__ = ["get_conversation_analyzer", "BaseConversationAnalyzer", "StageAnalysisResult"]
