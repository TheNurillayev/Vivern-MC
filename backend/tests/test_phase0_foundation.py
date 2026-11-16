import asyncio
import os
import hmac
import hashlib
import time
from urllib.parse import urlencode
from backend.app.core.config import settings
from backend.app.core.security import verify_telegram_init_data, is_admin_user
from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.models.user import User
from sqlalchemy import select
from backend.app.main import app
from fastapi.testclient import TestClient

def test_secrets_isolation():
    """Verify secrets are isolated server-side and .env.example contains no real tokens."""
    assert os.path.exists(".env"), ".env file must exist on server"
    assert os.path.exists(".env.example"), ".env.example file must exist"

    with open(".env.example", "r", encoding="utf-8") as f:
        example_content = f.read()

    # Ensure no real bot token is in .env.example
    assert "9067530471" not in example_content, ".env.example must not contain real bot token!"
    assert "your_telegram_bot_token_here" in example_content

def test_telegram_init_data_validation():
    """Verify HMAC-SHA256 signature algorithm against Telegram specification."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    assert bot_token, "Bot token must be configured"

    # Construct test data
    auth_date = str(int(time.time()))
    user_str = '{"id":8449563084,"first_name":"AdminUser","username":"admin"}'

    params = {
        "auth_date": auth_date,
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_str
    }

    # Generate valid hash
    items = sorted(params.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    valid_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    params_with_hash = dict(params)
    params_with_hash["hash"] = valid_hash
    valid_query = urlencode(params_with_hash)

    # Test 1: Valid initData must succeed
    verified = verify_telegram_init_data(valid_query)
    assert verified is not None, "Valid Telegram initData must verify successfully"
    assert verified["id"] == 8449563084
    assert is_admin_user(verified["id"]) is True

    # Test 2: Tampered hash must be rejected
    params_tampered = dict(params)
    params_tampered["hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
    tampered_query = urlencode(params_tampered)
    assert verify_telegram_init_data(tampered_query) is None, "Tampered hash must be rejected"

def test_health_endpoint():
    """Verify health check endpoint returns 200 and correct diagnostics."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["database"]["connected"] is True
    assert data["ffmpeg"]["available"] is True
    assert data["bot"]["configured"] is True

def test_user_database_model():
    """Verify database async model creation and user record insertion."""
    async def run():
        await init_db()
        async with AsyncSessionLocal() as session:
            test_uid = 8449563084
            res = await session.execute(select(User).where(User.id == test_uid))
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    id=test_uid,
                    first_name="Admin",
                    last_name="Owner",
                    username="owner",
                    is_admin=True,
                    trial_count=0
                )
                session.add(user)
                await session.commit()
            assert user.id == test_uid

    asyncio.run(run())

if __name__ == "__main__":
    print("Running Phase 0 acceptance tests...")
    test_secrets_isolation()
    print("PASS: Secrets isolation & .env.example check")

    test_telegram_init_data_validation()
    print("PASS: Telegram HMAC-SHA256 initData validation (AT-01)")

    test_health_endpoint()
    print("PASS: Backend health check endpoint")

    test_user_database_model()
    print("PASS: Database User model & table initialization")

    print("\nALL PHASE 0 ACCEPTANCE TESTS PASSED!")
