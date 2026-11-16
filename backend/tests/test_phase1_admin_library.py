import os
import io
import wave
import struct
import math
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.api.auth import create_session_token

def generate_test_wav(duration_seconds: float = 2.0, freq: float = 440.0) -> bytes:
    """Generate a valid standard PCM WAV in memory for tests."""
    sample_rate = 44100
    n_samples = int(sample_rate * duration_seconds)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1) # mono
        wav.setsampwidth(2) # 16-bit
        wav.setframerate(sample_rate)
        for i in range(n_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            wav.writeframes(struct.pack('<h', val))
    buf.seek(0)
    return buf.read()

def test_admin_protection_at_02():
    """AT-02: Customer cannot access admin UI/API (returns 401/403)."""
    client = TestClient(app)

    # 1. Unauthenticated request -> 401
    res = client.get("/api/admin/categories")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"

    # 2. Register a normal customer user
    auth_res = client.post("/api/auth/telegram", json={"init_data": "test_user_999999999"})
    assert auth_res.status_code == 200
    customer_token = auth_res.json()["token"]

    # 3. Normal customer accessing admin endpoint -> 403 Forbidden
    res_customer = client.get("/api/admin/categories", headers={"Authorization": f"Bearer {customer_token}"})
    assert res_customer.status_code == 403, f"Expected 403 Forbidden for non-admin, got {res_customer.status_code}"

def test_admin_library_operations_at_03():
    """AT-03: Admin manages all four categories, uploads, validates media, and previews tracks."""
    client = TestClient(app)
    admin_id = next(iter(settings.admin_ids))
    admin_token = create_session_token(user_id=admin_id, is_admin=True)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Check admin access endpoint
    auth_admin = client.post("/api/auth/telegram", json={"init_data": f"test_user_{admin_id}"})
    assert auth_admin.status_code == 200
    headers = {"Authorization": f"Bearer {auth_admin.json()['token']}"}

    res_check = client.get("/api/admin/check", headers=headers)
    assert res_check.status_code == 200, f"Admin check failed: {res_check.text}"

    # 2. Upload valid audio tracks for all 4 categories
    categories = ["number_call", "starter", "wishes", "call_ending"]
    uploaded_asset_ids = {}

    for cat in categories:
        wav_data = generate_test_wav(duration_seconds=3.0, freq=500.0)
        files = {
            "file": (f"test_{cat}.wav", wav_data, "audio/wav")
        }
        data = {
            "title": f"Test {cat.capitalize()} Track",
            "category": cat,
            "set_active": "true"
        }
        res_upload = client.post("/api/admin/assets/upload", headers=headers, data=data, files=files)
        assert res_upload.status_code == 200, f"Upload for {cat} failed: {res_upload.text}"
        asset = res_upload.json()
        assert asset["category"] == cat
        assert asset["is_active"] is True
        assert asset["duration_seconds"] >= 2.9
        uploaded_asset_ids[cat] = asset["id"]

    # 3. Retrieve categories and verify active tracks
    res_cats = client.get("/api/admin/categories", headers=headers)
    assert res_cats.status_code == 200
    cats_data = res_cats.json()
    assert len(cats_data) == 4
    for item in cats_data:
        assert item["active_track"] is not None
        assert item["active_track"]["id"] == uploaded_asset_ids[item["id"]]

    # 4. Preview / Stream audio track
    sample_id = uploaded_asset_ids["starter"]
    res_stream = client.get(f"/api/admin/assets/{sample_id}/preview")
    assert res_stream.status_code == 200
    assert len(res_stream.content) > 0

    # 5. Reject corrupt or non-audio file
    corrupt_files = {
        "file": ("fake_audio.mp3", b"THIS_IS_NOT_AUDIO_DATA_AT_ALL", "audio/mpeg")
    }
    res_bad = client.post("/api/admin/assets/upload", headers=headers, data={"title": "Bad", "category": "starter"}, files=corrupt_files)
    assert res_bad.status_code == 400, "Corrupt audio must be rejected with 400"
    assert "validation failed" in res_bad.json()["detail"].lower()

if __name__ == "__main__":
    print("Running Phase 1 acceptance tests (AT-02, AT-03)...")
    test_admin_protection_at_02()
    print("PASS: AT-02 Admin protection (Unauthorized users blocked with 401/403)")

    test_admin_library_operations_at_03()
    print("PASS: AT-03 Admin library management (4 categories, media validation, preview)")

    print("\nALL PHASE 1 ACCEPTANCE TESTS PASSED!")
