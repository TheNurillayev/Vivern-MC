import os
import shutil
import tempfile
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.api.auth import get_current_user
from backend.app.models.user import User
from backend.app.models.order import Order
from backend.app.schemas.order import OrderCreateResponse, OrderDetailResponse
from backend.app.services.audio.validator import validate_audio_file, AudioValidationError
from backend.app.services.storage.local_storage import storage_service

router = APIRouter(prefix="/api/orders", tags=["orders"])

@router.post("/create", response_model=OrderCreateResponse)
async def create_order(
    original_recording: UploadFile = File(...),
    special_music: UploadFile = File(...),
    audio_title: Optional[str] = Form(None),
    is_video_mode: Optional[bool] = Form(False),
    video_photos: Optional[List[UploadFile]] = File(None),
    host_video: Optional[UploadFile] = File(None),
    host_video_position: Optional[str] = Form("intro"),
    custom_wishes_start_seconds: Optional[float] = Form(None),
    custom_call_ending_seconds: Optional[float] = Form(None),
    custom_starter_track_id: Optional[str] = Form(None),
    custom_wishes_track_id: Optional[str] = Form(None),
    custom_ending_track_id: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not original_recording or not special_music:
        raise HTTPException(
            status_code=400,
            detail="Ikkala fayl ham talab qilinadi: Telefon suhbati va Maxsus musiqa."
        )

    # Temporary validation for original recording
    orig_ext = os.path.splitext(original_recording.filename or "")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=orig_ext) as tmp_orig:
        tmp_orig_path = tmp_orig.name
        shutil.copyfileobj(original_recording.file, tmp_orig)

    try:
        orig_meta = validate_audio_file(tmp_orig_path)
    except AudioValidationError as e:
        if os.path.exists(tmp_orig_path):
            os.remove(tmp_orig_path)
        raise HTTPException(
            status_code=400,
            detail=f"Telefon suhbati audiosi yaroqsiz: {str(e)}"
        )

    # Temporary validation for special music
    spec_ext = os.path.splitext(special_music.filename or "")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=spec_ext) as tmp_spec:
        tmp_spec_path = tmp_spec.name
        shutil.copyfileobj(special_music.file, tmp_spec)

    try:
        spec_meta = validate_audio_file(tmp_spec_path)
    except AudioValidationError as e:
        if os.path.exists(tmp_orig_path):
            os.remove(tmp_orig_path)
        if os.path.exists(tmp_spec_path):
            os.remove(tmp_spec_path)
        raise HTTPException(
            status_code=400,
            detail=f"Maxsus musiqa audiosi yaroqsiz: {str(e)}"
        )

    # Check free trial eligibility (including gifts/extra_trials and save_trials pause)
    total_allowed = settings.FREE_TRIAL_GENERATIONS + (user.extra_trials or 0)
    is_free = (not user.save_trials) and (user.trial_count < total_allowed)

    required_coins = 20 if is_video_mode else 10
    unit_price = (settings.PRICE_PER_ORDER_SOM * 2) if is_video_mode else settings.PRICE_PER_ORDER_SOM

    if not is_free:
        user_coins = user.coins or 0
        if user_coins < required_coins:
            if os.path.exists(tmp_orig_path):
                os.remove(tmp_orig_path)
            if os.path.exists(tmp_spec_path):
                os.remove(tmp_spec_path)
            mode_label = "Video" if is_video_mode else "Audio"
            raise HTTPException(
                status_code=402,
                detail=f"Balansingizda yetarli tanga mavjud emas. {mode_label} tabrik buyurtmasi uchun {required_coins} ta tanga kerak. Iltimos, hisobingizni to'ldiring."
            )
        # Deduct coins from user balance
        user.coins = user_coins - required_coins

    price = 0 if is_free else unit_price
    initial_status = "queued"

    order_id = str(uuid.uuid4())

    # Save to persistent storage
    saved_orig_path = storage_service.save_customer_upload(
        source_path=tmp_orig_path,
        order_id=order_id,
        upload_type="recording",
        original_filename=original_recording.filename or "recording.mp3"
    )
    saved_spec_path = storage_service.save_customer_upload(
        source_path=tmp_spec_path,
        order_id=order_id,
        upload_type="special_music",
        original_filename=special_music.filename or "special.mp3"
    )

    # Cleanup temp
    if os.path.exists(tmp_orig_path):
        os.remove(tmp_orig_path)
    if os.path.exists(tmp_spec_path):
        os.remove(tmp_spec_path)

    # Handle Video Mode uploads (photos + host promo video)
    import json
    saved_photo_paths = []
    saved_host_video_path = ""

    if is_video_mode:
        valid_photos = [p for p in (video_photos or []) if p.filename and len(p.filename.strip()) > 0]
        if len(valid_photos) < 10:
            raise HTTPException(
                status_code=400,
                detail=f"Video tabrik uchun kamida 10 ta rasm yuklanishi kerak (hozir: {len(valid_photos)} ta)."
            )
        if len(valid_photos) > 70:
            valid_photos = valid_photos[:70]

        from PIL import Image
        for p_idx, p_file in enumerate(valid_photos):
            p_ext = os.path.splitext(p_file.filename or "")[1] or ".jpg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=p_ext) as tmp_p:
                tmp_p_path = tmp_p.name
                shutil.copyfileobj(p_file.file, tmp_p)

            try:
                with Image.open(tmp_p_path) as im:
                    im.verify()
            except Exception:
                if os.path.exists(tmp_p_path):
                    os.remove(tmp_p_path)
                continue

            saved_p_path = storage_service.save_customer_photo(
                source_path=tmp_p_path,
                order_id=order_id,
                index=p_idx,
                original_filename=p_file.filename or f"photo_{p_idx}.jpg"
            )
            saved_photo_paths.append(saved_p_path)
            if os.path.exists(tmp_p_path):
                os.remove(tmp_p_path)

        if len(saved_photo_paths) < 10:
            raise HTTPException(
                status_code=400,
                detail=f"Kamida 10 ta yaroqli rasm bo'lishi kerak. Qayta tekshirib yuklang."
            )

        if host_video and host_video.filename and len(host_video.filename.strip()) > 0:
            hv_ext = os.path.splitext(host_video.filename or "")[1] or ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=hv_ext) as tmp_hv:
                tmp_hv_path = tmp_hv.name
                shutil.copyfileobj(host_video.file, tmp_hv)

            saved_host_video_path = storage_service.save_host_video(
                source_path=tmp_hv_path,
                order_id=order_id,
                original_filename=host_video.filename or "host_video.mp4"
            )
            if os.path.exists(tmp_hv_path):
                os.remove(tmp_hv_path)

    # Create Order record in DB
    order = Order(
        id=order_id,
        user_id=user.id,
        status=initial_status,
        audio_title=(audio_title.strip() if audio_title else "")[:200],
        original_recording_path=saved_orig_path,
        original_recording_name=original_recording.filename or "recording.mp3",
        special_music_path=saved_spec_path,
        special_music_name=special_music.filename or "special.mp3",
        custom_wishes_start_seconds=custom_wishes_start_seconds,
        custom_call_ending_seconds=custom_call_ending_seconds,
        custom_starter_track_id=custom_starter_track_id,
        custom_wishes_track_id=custom_wishes_track_id,
        custom_ending_track_id=custom_ending_track_id,
        is_video_mode=bool(is_video_mode),
        video_photos_json=json.dumps(saved_photo_paths),
        host_video_path=saved_host_video_path,
        host_video_position=host_video_position or "intro",
        price_som=price,
        is_free_trial=is_free,
        is_paid=is_free  # Trial orders are automatically considered paid
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return OrderCreateResponse.model_validate(order)

@router.get("/my", response_model=List[OrderDetailResponse])
async def get_my_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """AT-11: Customer sees only their own orders."""
    res = await db.execute(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
    )
    orders = res.scalars().all()
    return [OrderDetailResponse.model_validate(o) for o in orders]

@router.get("/library-options")
async def get_library_options(
    db: AsyncSession = Depends(get_db)
):
    """Returns curated background music options for customers to choose and preview."""
    from backend.app.models.library_asset import LibraryAsset
    result = await db.execute(
        select(LibraryAsset)
        .where(LibraryAsset.category.in_(["starter", "wishes", "call_ending"]))
        .order_by(LibraryAsset.category, LibraryAsset.is_active.desc(), LibraryAsset.created_at.desc())
    )
    assets = result.scalars().all()
    categories = {"starter": [], "wishes": [], "call_ending": []}
    for a in assets:
        if a.category in categories:
            categories[a.category].append({
                "id": a.id,
                "title": a.title,
                "category": a.category,
                "duration_seconds": a.duration_seconds,
                "is_active": a.is_active,
                "preview_url": f"/api/orders/library-tracks/{a.id}/preview"
            })
    return categories

@router.get("/library-tracks/{asset_id}/preview")
async def preview_customer_library_track(
    asset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Audio preview stream for background tracks in customer UI."""
    from backend.app.models.library_asset import LibraryAsset
    result = await db.execute(select(LibraryAsset).where(LibraryAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset or not asset.storage_path:
        raise HTTPException(status_code=404, detail="Audio trek topilmadi")
    resolved_path = storage_service.resolve_asset_path(asset.storage_path)
    if not resolved_path:
        raise HTTPException(status_code=404, detail="Audio trek fayli topilmadi")
    return FileResponse(resolved_path, media_type="audio/mpeg", filename=asset.filename)

@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_order_detail(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Security check: only order owner or admin can inspect
    if order.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this order")

    return OrderDetailResponse.model_validate(order)

@router.get("/{order_id}/download")
async def download_output_audio(
    order_id: str,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order or not order.output_audio_path or not os.path.exists(order.output_audio_path):
        raise HTTPException(status_code=404, detail="Audio fayl hali tayyor emas yoki topilmadi")

    import re
    if order.audio_title and order.audio_title.strip():
        safe_title = re.sub(r'[^\w\s-]', '', order.audio_title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        filename = f"{safe_title}.mp3" if safe_title else f"Vivern_MC_{order_id[:8]}.mp3"
    else:
        filename = f"Vivern_MC_{order_id[:8]}.mp3"

    return FileResponse(
        order.output_audio_path,
        media_type="audio/mpeg",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/{order_id}/download-video")
async def download_output_video(
    order_id: str,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order or not order.output_video_path or not os.path.exists(order.output_video_path):
        raise HTTPException(status_code=404, detail="Video fayl hali tayyor emas yoki topilmadi")

    import re
    if order.audio_title and order.audio_title.strip():
        safe_title = re.sub(r'[^\w\s-]', '', order.audio_title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        filename = f"{safe_title}.mp4" if safe_title else f"Vivern_MC_Video_{order_id[:8]}.mp4"
    else:
        filename = f"Vivern_MC_Video_{order_id[:8]}.mp4"

    return FileResponse(
        order.output_video_path,
        media_type="video/mp4",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    if order.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Ruxsat berilmadi: siz bu buyurtma egasi emassiz")

    # Clean up physical files from disk
    files_to_clean = [
        order.original_recording_path,
        order.special_music_path,
        order.output_audio_path,
        order.output_video_path,
        order.host_video_path
    ]
    import json
    try:
        photos = json.loads(order.video_photos_json or "[]")
        if isinstance(photos, list):
            files_to_clean.extend(photos)
    except Exception:
        pass

    for f_path in files_to_clean:
        if f_path and os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass

    await db.delete(order)
    await db.commit()
    return {"success": True, "message": "Buyurtma muvaffaqiyatli o'chirildi"}

