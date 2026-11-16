from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class PaymentCheckoutResult(BaseModel):
    payment_id: str
    provider: str
    payment_url: str
    amount: int
    currency: str = "UZS"

class PaymentWebhookResult(BaseModel):
    valid: bool
    transaction_id: str
    order_id: str
    amount: int
    status: str # "paid", "failed", "pending"
    message: Optional[str] = None

class BasePaymentProvider(ABC):
    @abstractmethod
    async def create_checkout(self, order_id: str, amount: int) -> PaymentCheckoutResult:
        pass

    @abstractmethod
    async def process_webhook(self, data: Dict[str, Any], headers: Dict[str, str]) -> PaymentWebhookResult:
        pass
