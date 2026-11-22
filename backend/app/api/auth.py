import json
import base64
import hmac
import hashlib
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Header, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.core.security import verify_telegram_init_data, is_admin_user
from backend.app.schemas.auth import TelegramInitDataRequest, AuthResponse, UserInfo
from backend.app.models.user import User
from backend.app.models.gift import Gift

router = APIRouter(prefix="/api/auth", tags=["auth"])

def create_session_token(user_id: int, is_admin: bool) -> str:
    payload = json.dumps({"uid": user_id, "admin": is_admin}).encode("utf-8")
    signature = hmac.new(settings.JWT_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    token = f"{base64.urlsafe_b64encode(payload).decode('utf-8')}.{signature}"
    return token

def verify_session_token(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_bytes = base64.urlsafe_b64decode(parts[0].encode("utf-8"))
        expected_sig = hmac.new(settings.JWT_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, parts[1]):
            return None
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None

async def get_current_user(
    token: Optional[str] = Query(None),
    authorization: str = Header(None),
    x_telegram_init_data: str = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    user_id = None
    is_admin = False

    # 1. Check Bearer token first
    if authorization and authorization.startswith("Bearer "):
        t = authorization.replace("Bearer ", "").strip()
        data = verify_session_token(t)
        if data:
            user_id = data.get("uid")

    # 2. Check query param token (for <audio> elements / direct links)
    if not user_id and token:
        data = verify_session_token(token)
        if data:
            user_id = data.get("uid")

    # 3. If no valid token, check x_telegram_init_data header
    if not user_id and x_telegram_init_data:
        parsed = verify_telegram_init_data(x_telegram_init_data)
        if parsed:
            user_id = parsed.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Telegram authentication credentials")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized: User does not exist or session expired")

    if user.is_blocked and not (user.is_admin or user.id in settings.admin_ids):
        raise HTTPException(status_code=403, detail="Hisobingiz bloklangan. Iltimos, administrator bilan bog'laning.")

    return user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin and current_user.id not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    return current_user

@router.post("/telegram", response_model=AuthResponse)
async def authenticate_telegram(req: TelegramInitDataRequest, db: AsyncSession = Depends(get_db)):
    parsed_user = verify_telegram_init_data(req.init_data)

    # In local testing, allow fallback if testing outside Telegram
    if not parsed_user:
        # Check if dummy dev init_data for testing
        if req.init_data.startswith("test_user_"):
            try:
                t_id = int(req.init_data.replace("test_user_", ""))
                parsed_user = {
                    "id": t_id,
                    "first_name": "Test User",
                    "username": f"test_{t_id}"
                }
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid Telegram initData signature")
        else:
            raise HTTPException(status_code=400, detail="Invalid Telegram initData signature")

    telegram_id = int(parsed_user["id"])
    first_name = parsed_user.get("first_name", "")
    last_name = parsed_user.get("last_name", "")
    username = parsed_user.get("username", "")
    language_code = parsed_user.get("language_code", "uz")
    is_admin = is_admin_user(telegram_id)

    result = await db.execute(select(User).where(User.id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            language_code=language_code,
            is_admin=is_admin,
            trial_count=0
        )
        db.add(user)
    else:
        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        user.is_admin = is_admin

    await db.commit()
    await db.refresh(user)

    token = create_session_token(user.id, user.is_admin)

    avatar_url = None
    if user.avatar_path and os.path.exists(user.avatar_path):
        avatar_url = f"/api/auth/profile/avatar/{user.id}"

    return AuthResponse(
        success=True,
        user=UserInfo(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=user.language_code,
            trial_count=user.trial_count,
            extra_trials=user.extra_trials or 0,
            coins=user.coins or 0,
            save_trials=bool(user.save_trials),
            is_blocked=bool(user.is_blocked),
            is_admin=user.is_admin,
            avatar_url=avatar_url
        ),
        token=token
    )

@router.post("/profile/photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Rasm tanlanmadi")

    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail="Faqat rasm formatlari (.jpg, .jpeg, .png, .webp) qabul qilinadi"
        )

    avatars_dir = settings.storage_path / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    # Clean up previous avatar files for this user so only 1 photo exists
    for old_ext in allowed_exts:
        old_path = avatars_dir / f"avatar_{current_user.id}{old_ext}"
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

    target_filename = f"avatar_{current_user.id}{ext}"
    target_path = avatars_dir / target_filename

    max_size = 10 * 1024 * 1024  # 10MB
    size = 0
    with open(target_path, "wb") as buffer:
        while chunk := await file.read(1024 * 64):
            size += len(chunk)
            if size > max_size:
                buffer.close()
                if target_path.exists():
                    target_path.unlink()
                raise HTTPException(status_code=400, detail="Rasm hajmi 10MB dan oshmasligi kerak")
            buffer.write(chunk)

    current_user.avatar_path = str(target_path)
    await db.commit()
    await db.refresh(current_user)

    ts = int(time.time())
    return {
        "success": True,
        "avatar_url": f"/api/auth/profile/avatar/{current_user.id}?t={ts}"
    }

@router.get("/profile/avatar/{user_id}")
async def get_user_avatar(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user or not user.avatar_path or not os.path.exists(user.avatar_path):
        raise HTTPException(status_code=404, detail="Profil rasmi topilmadi")

    ext = os.path.splitext(user.avatar_path)[1].lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif"
    }
    media_type = media_types.get(ext, "image/jpeg")

    return FileResponse(
        user.avatar_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"}
    )

class UpdateProfileNameRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = ""

@router.patch("/profile/name")
async def update_profile_name(
    req: UpdateProfileNameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    clean_first = req.first_name.strip()
    if not clean_first:
        raise HTTPException(status_code=400, detail="Ism bo'sh bo'lishi mumkin emas")

    current_user.first_name = clean_first
    if req.last_name is not None:
        current_user.last_name = req.last_name.strip()

    await db.commit()
    await db.refresh(current_user)
    return {
        "success": True,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name
    }

@router.patch("/profile/toggle-save-trials")
async def toggle_save_trials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_user.save_trials = not bool(current_user.save_trials)
    await db.commit()
    await db.refresh(current_user)
    return {
        "success": True,
        "save_trials": current_user.save_trials
    }

@router.get("/profile/gifts")
async def get_my_gifts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        select(Gift).where(Gift.user_id == current_user.id).order_by(Gift.created_at.desc())
    )
    gifts = res.scalars().all()
    return [
        {
            "id": g.id,
            "title": g.title,
            "message": g.message,
            "trials_given": g.trials_given,
            "created_at": g.created_at.strftime("%Y-%m-%d %H:%M") if g.created_at else ""
        }
        for g in gifts
    ]

@router.get("/me", response_model=UserInfo)
async def get_my_info(
    current_user: User = Depends(get_current_user)
):
    avatar_url = None
    if current_user.avatar_path and os.path.exists(current_user.avatar_path):
        avatar_url = f"/api/auth/profile/avatar/{current_user.id}"
    return UserInfo(
        id=current_user.id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        username=current_user.username,
        language_code=current_user.language_code,
        trial_count=current_user.trial_count,
        extra_trials=current_user.extra_trials or 0,
        coins=current_user.coins or 0,
        save_trials=bool(current_user.save_trials),
        is_blocked=bool(current_user.is_blocked),
        is_admin=current_user.is_admin,
        avatar_url=avatar_url
    )

class NotifyCoinPaymentRequest(BaseModel):
    package_name: str
    coins: int
    amount_som: int

@router.post("/coins/notify-payment")
async def notify_coin_payment(
    req: NotifyCoinPaymentRequest,
    current_user: User = Depends(get_current_user)
):
    """Sends notification to Telegram admin when user reports they sent payment for coins."""
    try:
        from backend.app.bot.bot import bot
        user_name = f"{current_user.first_name} {current_user.last_name or ''}".strip()
        tg_handle = f"@{current_user.username}" if current_user.username else f"ID: {current_user.id}"
        admin_text = (
            f"💰 *Yangi Tangalar To'lovi So'rovi!*\n\n"
            f"👤 Foydalanuvchi: *{user_name}* ({tg_handle})\n"
            f"🆔 ID: `{current_user.id}`\n"
            f"📦 Paket: *{req.package_name}* (+{req.coins} tanga)\n"
            f"💵 Summa: *{req.amount_som:,} so'm*\n\n"
            f"Admin panel orqali foydalanuvchiga tangalarni tasdiqlab berishingiz mumkin."
        )
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        pass

    return {"success": True, "message": "Admin bildirishnoma qabul qildi"}

@router.post("/coins/submit-receipt")
async def submit_coin_receipt(
    file: UploadFile = File(...),
    package_name: str = Form(...),
    coins: int = Form(...),
    amount_som: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Uploads receipt file and sends structured notification with document/photo to admin via bot."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Chek fayli yuklanmadi")

    receipts_dir = settings.storage_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower()
    ts = int(time.time())
    saved_filename = f"receipt_{current_user.id}_{ts}{ext}"
    saved_path = receipts_dir / saved_filename

    with open(saved_path, "wb") as buffer:
        while chunk := await file.read(1024 * 64):
            buffer.write(chunk)

    is_image = ext in [".jpg", ".jpeg", ".png", ".webp"]
    user_name = f"{current_user.first_name} {current_user.last_name or ''}".strip()
    tg_handle = f"@{current_user.username}" if current_user.username else f"ID: {current_user.id}"

    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    caption = (
        f"🧾 *YANGI TO'LOV CHEKI KELDI!*\n\n"
        f"👤 *Foydalanuvchi:* {user_name} ({tg_handle})\n"
        f"🆔 *Telegram ID:* `{current_user.id}`\n"
        f"📦 *Tanlangan tarif:* {package_name}\n"
        f"🪙 *Qo'shilishi kerak:* +{coins} Tanga\n"
        f"💵 *To'lov summasi:* {amount_som:,} so'm\n"
        f"📅 *Sana:* {now_str}\n\n"
        f"_Admin panel orqali foydalanuvchiga tangalarni tasdiqlab berishingiz mumkin._"
    )

    try:
        from backend.app.bot.bot import send_receipt_to_admins
        await send_receipt_to_admins(str(saved_path), caption, is_image=is_image)
    except Exception as e:
        import logging
        logging.getLogger("vivern-auth").error(f"Failed to send receipt to admin: {e}")

    return {
        "success": True,
        "message": "To'lov cheki administratorga muvaffaqiyatli yetkazildi"
    }
