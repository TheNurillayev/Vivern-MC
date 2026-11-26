import os
import shutil
import tempfile
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, case
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.api.auth import get_admin_user
from backend.app.models.user import User
from backend.app.models.gift import Gift
from backend.app.models.library_asset import LibraryAsset
from backend.app.models.order import Order
from backend.app.schemas.library import LibraryAssetResponse
from backend.app.services.audio.validator import validate_audio_file, AudioValidationError
from backend.app.services.storage.local_storage import storage_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_CATEGORIES = {
    "number_call": "Number & Call Sounds (Keypad / Ringing)",
    "starter": "Starter Music for BG (Opening)",
    "wishes": "Wishes Music for BG (Birthday Wishes)",
    "call_ending": "Call Ending Music for BG (Ending)"
}

@router.get("/check")
async def check_admin_access(admin: User = Depends(get_admin_user)):
    return {
        "success": True,
        "admin_id": admin.id,
        "first_name": admin.first_name,
        "username": admin.username
    }

@router.get("/categories")
async def list_categories(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LibraryAsset).where(LibraryAsset.is_active == True))
    active_assets = result.scalars().all()
    active_map = {a.category: LibraryAssetResponse.model_validate(a) for a in active_assets}

    return [
        {
            "id": cat_id,
            "name": cat_name,
            "active_track": active_map.get(cat_id)
        }
        for cat_id, cat_name in VALID_CATEGORIES.items()
    ]

@router.get("/assets", response_model=List[LibraryAssetResponse])
async def list_assets(
    category: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(LibraryAsset).order_by(LibraryAsset.created_at.desc())
    if category:
        if category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail="Invalid category")
        query = query.where(LibraryAsset.category == category)

    result = await db.execute(query)
    assets = result.scalars().all()
    return [LibraryAssetResponse.model_validate(a) for a in assets]

@router.post("/assets/upload", response_model=LibraryAssetResponse)
async def upload_asset(
    title: str = Form(...),
    category: str = Form(...),
    set_active: bool = Form(True),
    file: UploadFile = File(...),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Allowed: {list(VALID_CATEGORIES.keys())}"
        )

    # Save to temp file for media inspection
    suffix = os.path.splitext(file.filename or "")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    try:
        # Validate media content with FFmpeg
        meta = validate_audio_file(tmp_path)
    except AudioValidationError as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=400, detail=f"Audio validation failed: {str(e)}")

    # Check current version count for safe replacement
    res = await db.execute(
        select(LibraryAsset).where(LibraryAsset.category == category).order_by(LibraryAsset.version.desc())
    )
    latest = res.scalars().first()
    new_version = (latest.version + 1) if latest else 1

    # Save versioned file to storage
    final_path = storage_service.save_library_asset(
        source_path=tmp_path,
        category=category,
        original_filename=file.filename or "audio.mp3",
        version=new_version
    )

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # If setting active, deactivate existing tracks in this category
    if set_active:
        await db.execute(
            update(LibraryAsset)
            .where(LibraryAsset.category == category)
            .values(is_active=False)
        )

    asset = LibraryAsset(
        category=category,
        title=title,
        filename=os.path.basename(final_path),
        storage_path=final_path,
        duration_seconds=meta["duration_seconds"],
        format=meta["format"],
        file_size_bytes=meta["file_size_bytes"],
        is_active=set_active,
        version=new_version,
        uploaded_by=str(admin.id)
    )

    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return LibraryAssetResponse.model_validate(asset)

@router.patch("/assets/{asset_id}/activate", response_model=LibraryAssetResponse)
async def activate_asset(
    asset_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(LibraryAsset).where(LibraryAsset.id == asset_id))
    asset = res.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Deactivate others in same category
    await db.execute(
        update(LibraryAsset)
        .where(LibraryAsset.category == asset.category)
        .values(is_active=False)
    )

    asset.is_active = True
    await db.commit()
    await db.refresh(asset)
    return LibraryAssetResponse.model_validate(asset)

class RenameAssetRequest(BaseModel):
    title: str

@router.patch("/assets/{asset_id}/rename", response_model=LibraryAssetResponse)
async def rename_asset(
    asset_id: str,
    req: RenameAssetRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    cleaned_title = req.title.strip()
    if not cleaned_title:
        raise HTTPException(status_code=400, detail="Trek nomi bo'sh bo'lishi mumkin emas")

    res = await db.execute(select(LibraryAsset).where(LibraryAsset.id == asset_id))
    asset = res.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Trek topilmadi")

    asset.title = cleaned_title
    await db.commit()
    await db.refresh(asset)
    return LibraryAssetResponse.model_validate(asset)

@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(LibraryAsset).where(LibraryAsset.id == asset_id))
    asset = res.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Do not hard delete active track if it's the only one
    storage_service.delete_file(asset.storage_path)
    await db.delete(asset)
    await db.commit()

    return {"success": True, "deleted_id": asset_id}

@router.get("/assets/{asset_id}/preview")
async def preview_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(LibraryAsset).where(LibraryAsset.id == asset_id))
    asset = res.scalar_one_or_none()
    if not asset or not os.path.exists(asset.storage_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    media_type = f"audio/{asset.format}" if asset.format != "mp3" else "audio/mpeg"
    return FileResponse(asset.storage_path, media_type=media_type)

@router.get("/orders")
async def list_all_orders(
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Order).order_by(Order.created_at.desc())
    if status:
        query = query.where(Order.status == status)
    if user_id:
        query = query.where(Order.user_id == user_id)
    res = await db.execute(query)
    orders = res.scalars().all()
    return [
        {
            "id": o.id,
            "user_id": o.user_id,
            "status": o.status,
            "original_recording_name": o.original_recording_name,
            "special_music_name": o.special_music_name,
            "duration": o.output_audio_duration,
            "error_message": o.error_message,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else None,
            "completed_at": o.completed_at.strftime("%Y-%m-%d %H:%M") if o.completed_at else None
        }
        for o in orders
    ]

@router.post("/orders/{order_id}/retry")
async def retry_order(
    order_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "queued"
    order.error_message = ""
    await db.commit()
    return {"success": True, "message": f"Order {order_id} re-queued successfully"}

@router.get("/users")
async def list_admin_users(
    query: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List registered users with order counts, trials, and real-time search."""
    stmt = (
        select(
            User,
            func.count(Order.id).label("total_orders"),
            func.count(case((Order.status == "completed", 1))).label("completed_orders")
        )
        .outerjoin(Order, Order.user_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    users_list = []
    q = query.lower().strip() if query else None

    for user, total_orders, completed_orders in rows:
        fn = (user.first_name or "").lower()
        ln = (user.last_name or "").lower()
        un = (user.username or "").lower()
        uid_str = str(user.id)

        if q:
            clean_q = q.replace("@", "")
            if (q not in fn and q not in ln and q not in un 
                and q not in uid_str and clean_q not in un):
                continue

        users_list.append({
            "id": user.id,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "",
            "language_code": user.language_code or "uz",
            "trial_count": user.trial_count or 0,
            "extra_trials": user.extra_trials or 0,
            "coins": user.coins or 0,
            "save_trials": bool(user.save_trials),
            "is_blocked": bool(user.is_blocked),
            "is_admin": bool(user.is_admin or (user.id in settings.admin_ids)),
            "avatar_url": f"/api/auth/profile/avatar/{user.id}" if user.avatar_path else None,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else None,
            "total_orders": total_orders or 0,
            "completed_orders": completed_orders or 0
        })

    return users_list

@router.patch("/users/{user_id}/reset-trials")
async def reset_user_trials(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin trial reset / grant 3 free generations."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    user.trial_count = 0
    await db.commit()
    return {"success": True, "user_id": user_id, "trial_count": 0}

class SendGiftRequest(BaseModel):
    trials: int = 1
    title: Optional[str] = "🎁 Maxsus Sovg'a"
    message: Optional[str] = ""

@router.post("/users/{user_id}/gift")
async def send_user_gift(
    user_id: int,
    req: SendGiftRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin sends free trials and gift notification to a user."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    trials_to_add = max(1, req.trials)
    user.extra_trials = (user.extra_trials or 0) + trials_to_add

    gift = Gift(
        user_id=user_id,
        title=req.title or "🎁 Maxsus Sovg'a",
        message=req.message or "",
        trials_given=trials_to_add
    )
    db.add(gift)
    await db.commit()

    # Send telegram message to user if possible
    try:
        from backend.app.bot.bot import bot
        import html
        safe_title = html.escape(gift.title or "🎁 Maxsus Sovg'a")
        text = (
            f"🎉 <b>Sizga yangi sovg'a berildi!</b>\n\n"
            f"{safe_title}\n"
            f"✨ <b>Bonus:</b> +{trials_to_add} ta bepul audio montaj imkoniyati qo'shildi!\n"
        )
        if req.message:
            text += f"💬 <b>Xabar:</b> {html.escape(req.message)}\n"
        text += "\n<i>Ilovaga kirib, yangi bepul imkoniyatingizdan foydalanishingiz mumkin!</i> 🎂🎶"
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception:
        pass

    return {
        "success": True,
        "user_id": user_id,
        "extra_trials": user.extra_trials,
        "trials_given": trials_to_add
    }

@router.post("/users/{user_id}/toggle-block")
async def toggle_block_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin blocks or unblocks a user."""
    if user_id == admin.id or user_id in settings.admin_ids:
        raise HTTPException(status_code=400, detail="Administratorni bloklash mumkin emas")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    user.is_blocked = not bool(user.is_blocked)
    await db.commit()
    return {"success": True, "user_id": user_id, "is_blocked": user.is_blocked}

class AddCoinsRequest(BaseModel):
    coins: int = 10
    message: Optional[str] = ""

@router.post("/users/{user_id}/coins")
async def add_user_coins(
    user_id: int,
    req: AddCoinsRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin adds coins to user account and notifies user via Telegram."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    coins_to_add = req.coins
    user.coins = max(0, (user.coins or 0) + coins_to_add)
    try:
        from backend.app.models.coin_transaction import CoinTransaction
        tx = CoinTransaction(
            user_id=user_id,
            type="admin_add",
            coins=coins_to_add,
            amount_som=0,
            description=f"Admin tomonidan qo'shildi ({coins_to_add} Tanga)",
            status="completed"
        )
        db.add(tx)
    except Exception:
        pass
    await db.commit()
    await db.refresh(user)

    # Send telegram message to user if possible
    try:
        from backend.app.bot.bot import bot
        import html
        text = (
            f"🪙 <b>Hisobingizga tangalar qo'shildi!</b>\n\n"
            f"✨ Qo'shildi: <b>+{coins_to_add} ta tanga</b>\n"
            f"💰 Yangi balansingiz: <b>{user.coins} ta tanga</b>\n"
        )
        if req.message:
            text += f"💬 <b>Xabar:</b> {html.escape(req.message)}\n"
        text += f"\n<i>Har bir professional audio montaj narxi: 10 ta tanga.</i> 🎂🎶"
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception:
        pass

    return {
        "success": True,
        "user_id": user_id,
        "coins": user.coins,
        "added": coins_to_add
    }

@router.get("/users/{user_id}/payments")
async def get_user_payment_history(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns detailed payment history for a user: completed orders, free vs paid, and coin purchases."""
    from backend.app.models.coin_transaction import CoinTransaction

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    # Fetch orders
    orders_res = await db.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    )
    orders = orders_res.scalars().all()

    # Fetch coin transactions
    tx_res = await db.execute(
        select(CoinTransaction).where(CoinTransaction.user_id == user_id).order_by(CoinTransaction.created_at.desc())
    )
    transactions = tx_res.scalars().all()

    completed_orders = [o for o in orders if o.status == "completed"]
    total_allowed_trials = 3 + (user.extra_trials or 0)
    used_trials = min(len(completed_orders), total_allowed_trials)
    paid_orders = max(0, len(completed_orders) - used_trials)
    paid_orders_som = paid_orders * 5000

    tx_total_som = sum(t.amount_som for t in transactions if t.status == "completed")
    tx_total_coins = sum(t.coins for t in transactions if t.status == "completed" and t.coins > 0)

    effective_total_paid = max(user.total_paid_som or 0, tx_total_som) + paid_orders_som
    effective_total_coins = max(user.coins or 0, tx_total_coins)

    return {
        "user_id": user_id,
        "completed_orders_count": len(completed_orders),
        "used_trials": used_trials,
        "paid_orders": paid_orders,
        "total_allowed_trials": total_allowed_trials,
        "total_paid_som": effective_total_paid,
        "total_coins": effective_total_coins,
        "current_coins": user.coins or 0,
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "coins": t.coins,
                "amount_som": t.amount_som,
                "description": t.description,
                "status": t.status,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""
            }
            for t in transactions
        ],
        "orders": [
            {
                "id": o.id,
                "name": o.special_music_name or o.audio_title or "Tabrik",
                "status": o.status,
                "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else ""
            }
            for o in orders
        ]
    }

@router.get("/costs/summary")
async def get_cost_summary(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """AT-15 Cost Tracking: Returns aggregated operational costs and resource metrics."""
    res = await db.execute(select(Order))
    orders = res.scalars().all()

    total_orders = len(orders)
    completed_orders = sum(1 for o in orders if o.status == "completed")
    total_minutes = sum(o.transcription_minutes for o in orders)
    total_cost_usd = sum(o.transcription_cost_usd + o.analysis_cost_usd for o in orders)
    total_storage = sum(o.storage_mb for o in orders)
    total_revenue = sum(o.price_som for o in orders if o.is_paid and not o.is_free_trial)
    total_time = sum(o.processing_time_seconds for o in orders)
    avg_time = round(total_time / completed_orders, 2) if completed_orders > 0 else 0.0

    return {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_transcription_minutes": round(total_minutes, 2),
        "total_provider_cost_usd": round(total_cost_usd, 4),
        "total_storage_mb": round(total_storage, 2),
        "total_revenue_som": total_revenue,
        "average_processing_seconds": avg_time
    }
