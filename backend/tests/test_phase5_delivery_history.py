import asyncio
import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.app.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.order import Order
from backend.app.worker import process_single_order
from backend.tests.test_phase1_admin_library import generate_test_wav

def test_order_worker_processing_and_delivery_at_10_14():
    """AT-10, AT-14: Background worker processes queued order and delivers to Telegram."""
    client = TestClient(app)

    # 1. Register customer
    user_id = 7770001
    auth_res = client.post("/api/auth/telegram", json={"init_data": f"test_user_{user_id}"})
    token = auth_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Order
    rec_wav = generate_test_wav(duration_seconds=10.0, freq=440.0)
    spec_wav = generate_test_wav(duration_seconds=6.0, freq=660.0)

    files = {
        "original_recording": ("birthday_call.wav", rec_wav, "audio/wav"),
        "special_music": ("favorite_song.wav", spec_wav, "audio/wav"),
    }
    create_res = client.post("/api/orders/create", headers=headers, files=files)
    assert create_res.status_code == 200
    order_id = create_res.json()["id"]

    # 3. Process order in worker (with mocked Telegram bot delivery to test without live network call)
    mock_msg = AsyncMock()
    mock_msg.message_id = 998877

    with patch("backend.app.worker.send_delivery_audio", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_msg

        asyncio.run(process_single_order(order_id))

        # Check delivery function called with correct chat_id and audio path
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["chat_id"] == user_id
        assert os.path.exists(call_kwargs["audio_path"])
        assert "Tug'ilgan kun" in call_kwargs["caption"]

    # 4. Verify order in DB and via customer history API (AT-11)
    res_orders = client.get("/api/orders/my", headers=headers)
    assert res_orders.status_code == 200
    my_orders = res_orders.json()
    matched = next((o for o in my_orders if o["id"] == order_id), None)
    assert matched is not None, "Order must appear in customer history"
    assert matched["status"] == "completed"
    assert matched["output_audio_duration"] > 0
    assert matched["delivered_to_telegram"] is True

    # 5. Verify download endpoint serves the rendered audio
    res_dl = client.get(f"/api/orders/{order_id}/download", headers=headers)
    assert res_dl.status_code == 200
    assert len(res_dl.content) > 1000

if __name__ == "__main__":
    print("Running Phase 5 acceptance tests (AT-10, AT-11, AT-14)...")
    test_order_worker_processing_and_delivery_at_10_14()
    print("PASS: AT-10 Delivery into correct Telegram user chat")
    print("PASS: AT-11 Customer order history and audio download")
    print("PASS: AT-14 Background processing lifecycle")

    print("\nALL PHASE 5 ACCEPTANCE TESTS PASSED!")
