import datetime
import uuid
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base

class CoinTransaction(Base):
    __tablename__ = "coin_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), default="purchase") # purchase, admin_gift, admin_add, spend
    coins: Mapped[int] = mapped_column(Integer, default=0)
    amount_som: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="completed") # completed, pending, cancelled
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
