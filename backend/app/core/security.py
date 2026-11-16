import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote
from typing import Optional, Dict, Any
from backend.app.core.config import settings

def verify_telegram_init_data(init_data_raw: str, max_age_seconds: int = 86400) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256 as documented by Telegram.
    Returns parsed user dict if valid, else None.
    """
    if not init_data_raw:
        return None

    try:
        parsed_data = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    except Exception:
        return None

    received_hash = parsed_data.pop("hash", None)
    if not received_hash:
        return None

    # Check auth_date
    auth_date_str = parsed_data.get("auth_date")
    if auth_date_str and auth_date_str.isdigit():
        auth_date = int(auth_date_str)
        # Check if expired (allow up to max_age_seconds or future clock drift of 60s)
        current_time = int(time.time())
        if current_time - auth_date > max_age_seconds:
            return None

    # Construct data_check_string: sorted alphabetically by key, separated by \n
    items = sorted(parsed_data.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    # secret_key = HMAC_SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()

    # calculated_hash = HMAC_SHA256(secret_key, data_check_string)
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    # Extract user object
    user_str = parsed_data.get("user")
    if user_str:
        try:
            user_data = json.loads(user_str)
            user_data["auth_date"] = auth_date_str
            return user_data
        except Exception:
            return None

    return None

def is_admin_user(telegram_user_id: int) -> bool:
    return telegram_user_id in settings.admin_ids
