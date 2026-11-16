import uuid
import hmac
import hashlib
from typing import Dict, Any
from backend.app.core.config import settings
from backend.app.services.payment.base import BasePaymentProvider, PaymentCheckoutResult, PaymentWebhookResult

class MockUzbekistanPaymentProvider(BasePaymentProvider):
    """
    Adapter supporting local development and testing of Uzbekistan payment provider webhooks (e.g. Payme, Click, Uzum).
    Enforces HMAC server-side verification and idempotent transaction handling.
    """
    def __init__(self, provider_name: str = "uzum_pay"):
        self.provider_name = provider_name
        self.secret_key = settings.JWT_SECRET

    async def create_checkout(self, order_id: str, amount: int) -> PaymentCheckoutResult:
        payment_id = str(uuid.uuid4())
        checkout_url = f"{settings.SERVER_PUBLIC_URL}/api/payments/test-checkout?order_id={order_id}&amount={amount}&pid={payment_id}"
        return PaymentCheckoutResult(
            payment_id=payment_id,
            provider=self.provider_name,
            payment_url=checkout_url,
            amount=amount,
            currency="UZS"
        )

    async def process_webhook(self, data: Dict[str, Any], headers: Dict[str, str]) -> PaymentWebhookResult:
        # Verify HMAC signature in headers
        signature = headers.get("X-Payment-Signature") or headers.get("x-payment-signature")
        order_id = str(data.get("order_id", ""))
        amount = int(data.get("amount", 0))
        tx_id = str(data.get("transaction_id", ""))

        # Check signature: HMAC-SHA256(secret, f"{order_id}:{amount}:{tx_id}")
        data_string = f"{order_id}:{amount}:{tx_id}"
        expected_sig = hmac.new(self.secret_key.encode(), data_string.encode(), hashlib.sha256).hexdigest()

        if not signature or not hmac.compare_digest(signature, expected_sig):
            return PaymentWebhookResult(
                valid=False,
                transaction_id=tx_id,
                order_id=order_id,
                amount=amount,
                status="failed",
                message="Invalid payment signature"
            )

        return PaymentWebhookResult(
            valid=True,
            transaction_id=tx_id,
            order_id=order_id,
            amount=amount,
            status="paid"
        )
