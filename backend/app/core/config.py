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

    SPEECH_PROVIDER: str = os.getenv("SPEECH_PROVIDER", "gladia")
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    ANALYSIS_PROVIDER: str = os.getenv("ANALYSIS_PROVIDER", "deepseek")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GLADIA_API_KEY: str = os.getenv("GLADIA_API_KEY", "")

    PRICE_PER_ORDER_SOM: int = 5000
    FREE_TRIAL_GENERATIONS: int = 3
    JWT_SECRET: str = "vivern_mc_default_secret_key"

    @property
    def BASE_DIR(self) -> Path:
        return BASE_DIR

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
        # Detect Railway Volume mount path if attached by user in Railway
        railway_vol = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
        if railway_vol and railway_vol.strip():
            p = Path(railway_vol.strip())
        elif os.path.exists("/app/storage") and os.path.ismount("/app/storage"):
            p = Path("/app/storage")
        elif os.path.exists("/storage") and os.path.ismount("/storage"):
            p = Path("/storage")
        elif os.path.exists("/data") and os.path.ismount("/data"):
            p = Path("/data")
        else:
            raw_storage = os.getenv("STORAGE_DIR", self.STORAGE_DIR)
            p = Path(raw_storage)
            if not p.is_absolute():
                p = BASE_DIR / raw_storage
        p.mkdir(parents=True, exist_ok=True)
        (p / "library").mkdir(exist_ok=True)
        (p / "uploads").mkdir(exist_ok=True)
        (p / "outputs").mkdir(exist_ok=True)
        (p / "avatars").mkdir(exist_ok=True)
        return p

    @property
    def resolved_database_url(self) -> str:
        url = os.getenv("DATABASE_URL", self.DATABASE_URL)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite"):
            raw = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if not Path(raw).is_absolute():
                db_name = Path(raw).name or "vivern.db"
                db_file = self.storage_path / db_name
                return f"sqlite+aiosqlite:///{db_file.as_posix()}"
        return url

settings = Settings()
