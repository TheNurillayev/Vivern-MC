import io
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.tests.test_phase1_admin_library import generate_test_wav

def test_upload_and_order_creation_at_04():
    """AT-04: Customer uploads original recording and special music; valid files create queued order."""
    client = TestClient(app)

    # Register Customer A
    auth_a = client.post("/api/auth/telegram", json={"init_data": "test_user_111001"})
    assert auth_a.status_code == 200
    token_a = auth_a.json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Generate test audio files
    recording_wav = generate_test_wav(duration_seconds=5.0, freq=440.0)
    music_wav = generate_test_wav(duration_seconds=4.0, freq=880.0)

    files = {
        "original_recording": ("phone_call.wav", recording_wav, "audio/wav"),
        "special_music": ("birthday_song.wav", music_wav, "audio/wav"),
    }

    res = client.post("/api/orders/create", headers=headers_a, files=files)
    assert res.status_code == 200, f"Order creation failed: {res.text}"
    order_data = res.json()

    assert "id" in order_data
    assert order_data["status"] == "queued"
    assert order_data["is_free_trial"] is True
    assert order_data["price_som"] == 0
    assert order_data["original_recording_name"] == "phone_call.wav"
    assert order_data["special_music_name"] == "birthday_song.wav"

    return order_data["id"], token_a

def test_invalid_file_rejection():
    """Invalid or corrupt file must return 400 with clear error."""
    client = TestClient(app)
    auth_a = client.post("/api/auth/telegram", json={"init_data": "test_user_111001"})
    token_a = auth_a.json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    valid_wav = generate_test_wav(duration_seconds=2.0)
    corrupt_bytes = b"NOT_A_VALID_AUDIO_FILE_DATA"

    # Corrupt original recording
    files = {
        "original_recording": ("broken.mp3", corrupt_bytes, "audio/mpeg"),
        "special_music": ("valid.wav", valid_wav, "audio/wav"),
    }
    res = client.post("/api/orders/create", headers=headers_a, files=files)
    assert res.status_code == 400
    assert "yaroqsiz" in res.json()["detail"].lower()

def test_order_history_isolation_at_11():
    """AT-11: Customer sees only own orders; orders of other customers are isolated."""
    client = TestClient(app)

    # Customer 1
    auth_1 = client.post("/api/auth/telegram", json={"init_data": "test_user_200001"})
    token_1 = auth_1.json()["token"]
    headers_1 = {"Authorization": f"Bearer {token_1}"}

    # Customer 2
    auth_2 = client.post("/api/auth/telegram", json={"init_data": "test_user_200002"})
    token_2 = auth_2.json()["token"]
    headers_2 = {"Authorization": f"Bearer {token_2}"}

    # Customer 1 creates an order
    rec_wav = generate_test_wav(duration_seconds=3.0)
    files = {
        "original_recording": ("user1_call.wav", rec_wav, "audio/wav"),
        "special_music": ("user1_song.wav", rec_wav, "audio/wav"),
    }
    res_create = client.post("/api/orders/create", headers=headers_1, files=files)
    assert res_create.status_code == 200
    order_1_id = res_create.json()["id"]

    # Customer 1 retrieves orders: must see order_1_id
    res_orders_1 = client.get("/api/orders/my", headers=headers_1)
    assert res_orders_1.status_code == 200
    ids_1 = [o["id"] for o in res_orders_1.json()]
    assert order_1_id in ids_1

    # Customer 2 retrieves orders: must NOT see Customer 1's order
    res_orders_2 = client.get("/api/orders/my", headers=headers_2)
    assert res_orders_2.status_code == 200
    ids_2 = [o["id"] for o in res_orders_2.json()]
    assert order_1_id not in ids_2, "Customer 2 must not see Customer 1's order!"

    # Customer 2 attempts to directly access Customer 1's order: must get 403 Forbidden
    res_direct = client.get(f"/api/orders/{order_1_id}", headers=headers_2)
    assert res_direct.status_code == 403, f"Expected 403, got {res_direct.status_code}"

if __name__ == "__main__":
    print("Running Phase 2 acceptance tests (AT-04, AT-11)...")
    test_upload_and_order_creation_at_04()
    print("PASS: AT-04 Customer upload scope & order creation")

    test_invalid_file_rejection()
    print("PASS: Clear rejection of corrupt/invalid audio files")

    test_order_history_isolation_at_11()
    print("PASS: AT-11 Order history customer privacy & isolation")

    print("\nALL PHASE 2 ACCEPTANCE TESTS PASSED!")
