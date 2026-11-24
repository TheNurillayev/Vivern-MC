import datetime
import uuid
from sqlalchemy import BigInteger, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)

    # Statuses: draft, uploading, queued, transcribing, analysing, review_required, rendering, payment_required, completed, failed, cancelled
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)

    # Input file paths
    audio_title: Mapped[str] = mapped_column(String(255), default="")
    original_recording_path: Mapped[str] = mapped_column(String(512), default="")
    original_recording_name: Mapped[str] = mapped_column(String(255), default="")
    special_music_path: Mapped[str] = mapped_column(String(512), default="")
    special_music_name: Mapped[str] = mapped_column(String(255), default="")

    # Custom timings (if specified by customer)
    custom_wishes_start_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    custom_call_ending_seconds: Mapped[float] = mapped_column(Float, nullable=True)

    # Custom background library tracks (if chosen by customer)
    custom_starter_track_id: Mapped[str] = mapped_column(String(36), nullable=True)
    custom_wishes_track_id: Mapped[str] = mapped_column(String(36), nullable=True)
    custom_ending_track_id: Mapped[str] = mapped_column(String(36), nullable=True)

    # Video Mode fields
    is_video_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    video_photos_json: Mapped[str] = mapped_column(Text, default="[]")
    host_video_path: Mapped[str] = mapped_column(String(512), default="")
    host_video_position: Mapped[str] = mapped_column(String(32), default="intro")
    output_video_path: Mapped[str] = mapped_column(String(512), default="")
    output_video_duration: Mapped[float] = mapped_column(Float, default=0.0)

    # Output file paths
    output_audio_path: Mapped[str] = mapped_column(String(512), default="")
    output_audio_duration: Mapped[float] = mapped_column(Float, default=0.0)

    # Pricing & trial
    price_som: Mapped[int] = mapped_column(Integer, default=5000)
    is_free_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    # Delivery status
    delivered_to_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    # Operational metrics and logs
    error_message: Mapped[str] = mapped_column(Text, default="")
    transcription_text: Mapped[str] = mapped_column(Text, default="")
    processing_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Cost Tracking metrics (AT-15)
    transcription_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    transcription_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    analysis_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    storage_mb: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    user = relationship("User", back_populates="orders")
    edit_decision = relationship("EditDecision", back_populates="order", uselist=False, cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
