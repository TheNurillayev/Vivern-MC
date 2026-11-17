import os
from pathlib import Path
from typing import List, Set
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8000")))
    SERVER_PUBLIC_URL: str = "http://localhost:8000"

    TELEGRAM_BOT_TOKEN: str
    ADMIN_TELEGRAM_IDS: str = "8449563084"

    DATABASE_URL: str = "sqlite+aiosqlite:///storage/vivern.db"
    STORAGE_DIR: str = "storage"

    SPEECH_PROVIDER: str = "mock"
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    ANALYSIS_PROVIDER: str = "heuristic"
    OPENAI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    PRICE_PER_ORDER_SOM: int = 5000
    FREE_TRIAL_GENERATIONS: int = 5
    JWT_SECRET: str = "vivern_mc_default_secret_key"

    @property
    def admin_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for item in self.ADMIN_TELEGRAM_IDS.split(","):
            cleaned = item.strip()
            if cleaned and cleaned.isdigit():
                ids.add(int(cleaned))
        return ids

    @property
    def storage_path(self) -> Path:
        p = BASE_DIR / self.STORAGE_DIR
        p.mkdir(parents=True, exist_ok=True)
        (p / "library").mkdir(exist_ok=True)
        (p / "uploads").mkdir(exist_ok=True)
        (p / "outputs").mkdir(exist_ok=True)
        return p

settings = Settings()
