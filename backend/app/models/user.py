from typing import Optional
import datetime
from sqlalchemy import BigInteger, String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # Telegram User ID
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    language_code: Mapped[str] = mapped_column(String(16), default="uz")
    trial_count: Mapped[int] = mapped_column(Integer, default=0) # Number of free generations used
    extra_trials: Mapped[int] = mapped_column(Integer, default=0) # Extra bonus/gift trials
    coins: Mapped[int] = mapped_column(Integer, default=0) # Coin balance (10 coins per order)
    total_paid_som: Mapped[int] = mapped_column(Integer, default=0) # Total amount paid in UZS
    save_trials: Mapped[bool] = mapped_column(Boolean, default=False) # True = save trials for later (deactivated)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False) # Admin ban status
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
