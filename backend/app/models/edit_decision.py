import datetime
import uuid
from sqlalchemy import String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base

class EditDecision(Base):
    __tablename__ = "edit_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), unique=True)

    language: Mapped[str] = mapped_column(String(16), default="uz")

    # Transitions proposed by analysis (in seconds)
    wishes_start_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    call_ending_start_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Confidences (0.0 to 1.0)
    wishes_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    call_ending_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    overall_confidence: Mapped[float] = mapped_column(Float, default=1.0)

    warnings: Mapped[str] = mapped_column(Text, default="")
    transcript_segments_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_assets_json: Mapped[str] = mapped_column(Text, default="{}")
    render_params_json: Mapped[str] = mapped_column(Text, default="{}")

    # Admin review adjustments if any
    is_reviewed_by_admin: Mapped[bool] = mapped_column(default=False)
    admin_notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    order = relationship("Order", back_populates="edit_decision")
