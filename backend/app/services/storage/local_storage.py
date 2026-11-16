import os
import shutil
import uuid
from pathlib import Path
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

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def delete_file(self, path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except Exception:
            pass
        return False

storage_service = LocalStorageService()
