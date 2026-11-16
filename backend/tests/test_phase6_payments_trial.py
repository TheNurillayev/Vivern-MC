import asyncio
import hmac
import hashlib
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.user import User
from backend.app.models.order import Order
from sqlalchemy import select
from backend.tests.test_phase1_admin_library import generate_test_wav

def test_free_trial_and_paid_transition():
    """Verify first 5 generations are free, 6th requires payment (5000 UZS)."""
    client = TestClient(app)

    import time
    user_id = 900000 + int(time.time() * 100) % 90000
    auth_res = client.post("/api/auth/telegram", json={"init_data": f"test_user_{user_id}"})
    token = auth_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    rec_wav = generate_test_wav(duration_seconds=2.0)
    spec_wav = generate_test_wav(duration_seconds=2.0)

    # 1. First order is free
    files = {
        "original_recording": ("call.wav", rec_wav, "audio/wav"),
        "special_music": ("song.wav", spec_wav, "audio/wav"),
    }
    res_1 = client.post("/api/orders/create", headers=headers, files=files)
    assert res_1.status_code == 200
    data_1 = res_1.json()
    assert data_1["is_free_trial"] is True
    assert data_1["price_som"] == 0
    assert data_1["status"] == "queued"

    # 2. Simulate user having used all 5 free trial generations
    async def set_trial_count_5():
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(User).where(User.id == user_id))
            u = res.scalar_one()
            u.trial_count = 5
            await session.commit()
    asyncio.run(set_trial_count_5())

    # 3. 6th order now requires payment
    files_6 = {
        "original_recording": ("call.wav", rec_wav, "audio/wav"),
        "special_music": ("song.wav", spec_wav, "audio/wav"),
    }
    res_6 = client.post("/api/orders/create", headers=headers, files=files_6)
    assert res_6.status_code == 200
    data_6 = res_6.json()
    assert data_6["is_free_trial"] is False
    assert data_6["price_som"] == 5000
    assert data_6["status"] == "payment_required"

    paid_order_id = data_6["id"]

    # 4. Request payment checkout
    res_checkout = client.post(f"/api/payments/checkout?order_id={paid_order_id}", headers=headers)
    assert res_checkout.status_code == 200
    checkout_data = res_checkout.json()
    assert "checkout_url" in checkout_data
    assert checkout_data["amount"] == 5000

    # 5. Payment Provider Webhook with HMAC signature
    tx_id = f"tx_uzum_{int(time.time() * 1000)}"
    amount = 5000
    payload = {
        "order_id": paid_order_id,
        "amount": amount,
        "transaction_id": tx_id
    }
    # Compute signature: HMAC-SHA256(secret, f"{order_id}:{amount}:{tx_id}")
    data_string = f"{paid_order_id}:{amount}:{tx_id}"
    signature = hmac.new(settings.JWT_SECRET.encode(), data_string.encode(), hashlib.sha256).hexdigest()

    webhook_headers = {"X-Payment-Signature": signature}
    res_webhook = client.post("/api/payments/webhook/uzum_pay", json=payload, headers=webhook_headers)
    assert res_webhook.status_code == 200
    assert res_webhook.json()["status"] == "confirmed"

    # Verify order is now paid and queued
    res_order = client.get(f"/api/orders/{paid_order_id}", headers=headers)
    assert res_order.status_code == 200
    assert res_order.json()["is_paid"] is True
    assert res_order.json()["status"] == "queued"

    # 6. Idempotency test: duplicate webhook must succeed without error or duplicate handling
    res_duplicate = client.post("/api/payments/webhook/uzum_pay", json=payload, headers=webhook_headers)
    assert res_duplicate.status_code == 200
    assert "idempotent" in res_duplicate.json()["message"].lower()

def test_failure_credit_policy_at_12():
    """AT-12: If an order fails, user trial counter is not consumed."""
    client = TestClient(app)

    import time
    user_id = 910000 + int(time.time() * 100) % 90000
    auth_res = client.post("/api/auth/telegram", json={"init_data": f"test_user_{user_id}"})
    token = auth_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Initial trial count = 0
    auth_data = client.post("/api/auth/telegram", json={"init_data": f"test_user_{user_id}"}).json()
    assert auth_data["user"]["trial_count"] == 0

    # Create order that fails in worker
    rec_wav = generate_test_wav(duration_seconds=2.0)
    spec_wav = generate_test_wav(duration_seconds=2.0)
    res_create = client.post(
        "/api/orders/create",
        headers=headers,
        files={"original_recording": ("c.wav", rec_wav, "audio/wav"), "special_music": ("s.wav", spec_wav, "audio/wav")}
    )
    order_id = res_create.json()["id"]

    # Simulate worker failure
    async def mark_failed():
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Order).where(Order.id == order_id))
            o = res.scalar_one()
            o.status = "failed"
            o.error_message = "Simulated render failure"
            await session.commit()
    asyncio.run(mark_failed())

    # Check that user trial count was NOT consumed (still 0)
    auth_check = client.post("/api/auth/telegram", json={"init_data": f"test_user_{user_id}"}).json()
    assert auth_check["user"]["trial_count"] == 0, "Failed order must not consume free trial count"

if __name__ == "__main__":
    print("Running Phase 6 acceptance tests (Payments & Trial Rules)...")
    test_free_trial_and_paid_transition()
    print("PASS: 5 Free Generations & 5000 UZS Paid Transition")
    print("PASS: Verified HMAC payment webhook & Idempotent handling")

    test_failure_credit_policy_at_12()
    print("PASS: AT-12 Failed job does not consume free trial")

    print("\nALL PHASE 6 ACCEPTANCE TESTS PASSED!")
