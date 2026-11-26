import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
from backend.app.core.config import settings

class LocalStorageService:
    def __init__(self):
        self.base_dir = settings.storage_path
        self.library_dir = self.base_dir / "library"
        self.uploads_dir = self.base_dir / "uploads"
        self.outputs_dir = self.base_dir / "outputs"

        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def save_library_asset(self, source_path: str, category: str, original_filename: str, version: int = 1) -> str:
        """
        Saves a library track with versioning to prevent breaking active jobs.
        Returns the absolute storage path.
        """
        ext = os.path.splitext(original_filename)[1].lower() or ".mp3"
        asset_id = uuid.uuid4().hex[:8]
        target_name = f"{category}_v{version}_{asset_id}{ext}"
        target_path = self.library_dir / target_name

        shutil.copy2(source_path, target_path)
        return str(target_path)

    def save_customer_upload(self, source_path: str, order_id: str, upload_type: str, original_filename: str) -> str:
        """
        Saves a customer uploaded file.
        Returns the absolute storage path.
        """
        ext = os.path.splitext(original_filename)[1].lower() or ".mp3"
        target_name = f"{order_id}_{upload_type}{ext}"
        target_path = self.uploads_dir / target_name

        shutil.copy2(source_path, target_path)
        return str(target_path)

    def get_output_path(self, order_id: str) -> str:
        return str(self.outputs_dir / f"vivern_order_{order_id}.mp3")

    def get_output_video_path(self, order_id: str) -> str:
        return str(self.outputs_dir / f"vivern_video_{order_id}.mp4")

    def save_customer_photo(self, source_path: str, order_id: str, index: int, original_filename: str) -> str:
        ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
        target_name = f"{order_id}_photo_{index:03d}{ext}"
        target_path = self.uploads_dir / target_name
        shutil.copy2(source_path, target_path)
        return str(target_path)

    def save_host_video(self, source_path: str, order_id: str, original_filename: str) -> str:
        ext = os.path.splitext(original_filename)[1].lower() or ".mp4"
        target_name = f"{order_id}_host_video{ext}"
        target_path = self.uploads_dir / target_name
        shutil.copy2(source_path, target_path)
        return str(target_path)

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def resolve_asset_path(self, raw_path: Optional[str]) -> Optional[str]:
        """
        Cross-platform resolver for media paths stored in DB (handles Windows <-> Linux
        path differences across local dev and Railway containers).
        """
        if not raw_path or not str(raw_path).strip():
            return None
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            return raw_path

        # Normalize filename
        filename = os.path.basename(str(raw_path).replace("\\", "/"))
        if not filename:
            return None

        # 1. Search storage/library
        cand1 = self.library_dir / filename
        if cand1.exists() and cand1.stat().st_size > 0:
            return str(cand1)

        # 2. Search storage/uploads
        cand2 = self.uploads_dir / filename
        if cand2.exists() and cand2.stat().st_size > 0:
            return str(cand2)

        # 3. Search storage root
        cand3 = self.base_dir / filename
        if cand3.exists() and cand3.stat().st_size > 0:
            return str(cand3)

        # 4. Search default_assets
        for base_cand in [
            Path(settings.BASE_DIR) / "default_assets" / "library" / filename,
            Path(settings.BASE_DIR) / "backend" / "default_assets" / "library" / filename,
            Path(os.getcwd()) / "MC - Source" / filename,
            Path(os.getcwd()) / "MC - Source" / "default_assets" / "library" / filename
        ]:
            if base_cand.exists() and base_cand.stat().st_size > 0:
                return str(base_cand)

        return None

    def delete_file(self, path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except Exception:
            pass
        return False

storage_service = LocalStorageService()
