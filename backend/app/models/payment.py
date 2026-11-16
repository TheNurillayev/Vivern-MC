import datetime
import uuid
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)

    provider: Mapped[str] = mapped_column(String(50), default="uzum_pay") # e.g., payme, click, uzum
    provider_transaction_id: Mapped[str] = mapped_column(String(128), default="")
    amount: Mapped[int] = mapped_column(Integer, default=5000)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")

    # Statuses: pending, paid, refunded, cancelled, failed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)

    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    confirmed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)

    order = relationship("Order", back_populates="payments")
