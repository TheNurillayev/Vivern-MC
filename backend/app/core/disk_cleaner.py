import os
import shutil
import time
import glob
import logging
import sqlite3
from pathlib import Path
from backend.app.core.config import settings

logger = logging.getLogger("vivern-disk-cleaner")

def get_disk_status():
    storage_path = settings.storage_path
    try:
        usage = shutil.disk_usage(str(storage_path))
        free_mb = round(usage.free / (1024 * 1024), 2)
        total_mb = round(usage.total / (1024 * 1024), 2)
        used_mb = round(usage.used / (1024 * 1024), 2)
        used_pct = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0
        return {
            "path": str(storage_path),
            "free_mb": free_mb,
            "total_mb": total_mb,
            "used_mb": used_mb,
            "used_pct": used_pct,
            "is_critical": free_mb < 200 or used_pct > 88
        }
    except Exception as e:
        logger.warning(f"Error checking disk usage: {e}")
        return {"error": str(e), "is_critical": False}

def run_disk_cleanup(force: bool = False):
    """
    Cleans up old uploads, temporary render files, orphaned files, and truncates SQLite WAL.
    Ensures Railway mounted volume never runs out of disk space.
    """
    storage_path = settings.storage_path
    status = get_disk_status()
    logger.info(f"Disk status before cleanup: {status}")

    freed_bytes = 0
    now = time.time()
    is_crit = force or status.get("is_critical", False)

    # 1. Clean /tmp directory for lingering ffmpeg/python artifacts
    for pattern in ["/tmp/tmp*", "/tmp/vivern*", "/tmp/slide*", "/tmp/*.mp4", "/tmp/*.wav", "/tmp/*.mp3", "/tmp/*.jpg", "/tmp/*.png"]:
        try:
            for p in glob.glob(pattern):
                try:
                    if os.path.isfile(p):
                        sz = os.path.getsize(p)
                        os.remove(p)
                        freed_bytes += sz
                    elif os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Clean storage/uploads
    # Photos and host videos from past orders can be safely removed if older than 2 hours (or 5 min if critical)
    uploads_dir = storage_path / "uploads"
    if uploads_dir.exists():
        max_age_sec = 1800 if not is_crit else 120  # 30 min normally, 2 min if critical
        for f in uploads_dir.iterdir():
            if f.is_file() and not f.name.endswith(".gitkeep"):
                try:
                    file_age = now - f.stat().st_mtime
                    # Prioritize cleaning photos, video clips, and older customer recordings
                    is_photo_or_video = ("_photo_" in f.name or "_host_video" in f.name or f.suffix.lower() in [".jpg", ".jpeg", ".png", ".mp4", ".mov"])
                    if is_crit or file_age > max_age_sec or (is_photo_or_video and file_age > 300):
                        sz = f.stat().st_size
                        f.unlink()
                        freed_bytes += sz
                except Exception:
                    pass

    # 3. Clean storage/outputs (keep recent ones, prune older than 24h or if disk is critical keep only last 5)
    outputs_dir = storage_path / "outputs"
    if outputs_dir.exists():
        output_files = []
        for f in outputs_dir.iterdir():
            if f.is_file() and not f.name.endswith(".gitkeep"):
                try:
                    output_files.append((f, f.stat().st_mtime, f.stat().st_size))
                except Exception:
                    pass

        # Sort by mtime descending (newest first)
        output_files.sort(key=lambda x: x[1], reverse=True)

        for idx, (f_path, f_mtime, f_size) in enumerate(output_files):
            file_age = now - f_mtime
            should_delete = False
            if is_crit and idx >= 3:
                should_delete = True
            elif file_age > (24 * 3600) and idx >= 8:
                should_delete = True

            if should_delete:
                try:
                    f_path.unlink()
                    freed_bytes += f_size
                except Exception:
                    pass

    # 4. Truncate SQLite WAL file
    db_file = None
    if settings.DATABASE_URL.startswith("sqlite"):
        raw = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        db_name = Path(raw).name or "vivern.db"
        db_file = storage_path / db_name

    if db_file and db_file.exists():
        try:
            conn = sqlite3.connect(str(db_file), timeout=10)
            cur = conn.cursor()
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            conn.commit()
            conn.close()
            logger.info("Successfully executed PRAGMA wal_checkpoint(TRUNCATE) on vivern.db")
        except Exception as e:
            logger.warning(f"Could not checkpoint WAL: {e}")

    after_status = get_disk_status()
    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    logger.info(f"Disk cleanup complete. Freed: ~{freed_mb} MB. After: {after_status}")
    return {
        "freed_mb": freed_mb,
        "before": status,
        "after": after_status
    }
