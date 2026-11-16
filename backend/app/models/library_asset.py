import datetime
import uuid
from sqlalchemy import String, Float, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base

class LibraryAsset(Base):
    __tablename__ = "library_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # category: 'number_call', 'starter', 'wishes', 'call_ending'
    category: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    format: Mapped[str] = mapped_column(String(32), default="mp3")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[int] = mapped_column(String(64), default="") # Admin Telegram ID
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
