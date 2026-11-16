from backend.app.core.config import settings
from backend.app.services.analysis.base import BaseConversationAnalyzer, StageAnalysisResult
from backend.app.services.analysis.heuristic_adapter import HeuristicConversationAnalyzer
from backend.app.services.analysis.openai_adapter import OpenAIConversationAnalyzer

def get_conversation_analyzer() -> BaseConversationAnalyzer:
    if settings.ANALYSIS_PROVIDER == "openai":
        return OpenAIConversationAnalyzer()
    return HeuristicConversationAnalyzer()

__all__ = ["get_conversation_analyzer", "BaseConversationAnalyzer", "StageAnalysisResult"]
