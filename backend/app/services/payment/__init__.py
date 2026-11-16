from backend.app.services.payment.base import BasePaymentProvider, PaymentCheckoutResult, PaymentWebhookResult
from backend.app.services.payment.mock_provider import MockUzbekistanPaymentProvider

def get_payment_provider(provider_name: str = "uzum_pay") -> BasePaymentProvider:
    return MockUzbekistanPaymentProvider(provider_name=provider_name)

__all__ = ["get_payment_provider", "BasePaymentProvider", "PaymentCheckoutResult", "PaymentWebhookResult"]
