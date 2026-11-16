import os
import time
import logging
from pathlib import Path
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

def cleanup_expired_files(retention_days: int = 30) -> dict:
    """
    Deletes temporary upload files and old rendered outputs older than retention_days.
    Preserves library assets.
    """
    now = time.time()
    cutoff_seconds = retention_days * 86400

    uploads_dir = settings.storage_path / "uploads"
    outputs_dir = settings.storage_path / "outputs"

    deleted_uploads = 0
    deleted_outputs = 0
    bytes_freed = 0

    for directory, counter_name in [(uploads_dir, "uploads"), (outputs_dir, "outputs")]:
        if not directory.exists():
            continue
        for item in directory.iterdir():
            if item.is_file() and not item.name.startswith("."):
                try:
                    mtime = item.stat().st_mtime
                    if now - mtime > cutoff_seconds:
                        size = item.stat().st_size
                        item.unlink()
                        bytes_freed += size
                        if counter_name == "uploads":
                            deleted_uploads += 1
                        else:
                            deleted_outputs += 1
                except Exception as e:
                    logger.warning(f"Could not delete {item}: {e}")

    logger.info(f"Retention cleanup finished: {deleted_uploads} uploads, {deleted_outputs} outputs deleted ({bytes_freed} bytes freed)")
    return {
        "retention_days": retention_days,
        "deleted_uploads": deleted_uploads,
        "deleted_outputs": deleted_outputs,
        "bytes_freed": bytes_freed
    }
