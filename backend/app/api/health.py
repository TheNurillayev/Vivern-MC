import os
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.app.core.database import get_db
from backend.app.core.config import settings
import imageio_ffmpeg

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # Check DB
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_err = str(e)

    # Check FFmpeg
    ffmpeg_ok = False
    ffmpeg_path = ""
    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_ok = os.path.exists(ffmpeg_path)
    except Exception:
        pass

    # Check Storage
    storage_ok = settings.storage_path.exists()

    return {
        "status": "healthy" if db_ok and ffmpeg_ok and storage_ok else "degraded",
        "service": "Vivern MC Audio Production Service",
        "version": "1.0.0",
        "database": {
            "connected": db_ok,
            "engine": "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql"
        },
        "ffmpeg": {
            "available": ffmpeg_ok,
            "path": ffmpeg_path
        },
        "storage": {
            "available": storage_ok,
            "path": str(settings.storage_path)
        },
        "bot": {
            "configured": bool(settings.TELEGRAM_BOT_TOKEN),
            "admin_count": len(settings.admin_ids)
        }
    }
