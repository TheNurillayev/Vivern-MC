import asyncio
import os
import logging
import time
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.config import settings
from backend.app.models.order import Order
from backend.app.models.user import User
from backend.app.models.library_asset import LibraryAsset
from backend.app.models.edit_decision import EditDecision
from backend.app.services.speech import get_speech_recognizer
from backend.app.services.analysis import get_conversation_analyzer
from backend.app.services.audio.renderer import audio_renderer
from backend.app.bot.bot import send_delivery_audio

logger = logging.getLogger("vivern-worker")

async def get_active_asset_path(category: str, session: AsyncSession) -> str:
    res = await session.execute(
        select(LibraryAsset)
        .where(LibraryAsset.category == category, LibraryAsset.is_active == True)
        .order_by(LibraryAsset.version.desc())
    )
    asset = res.scalars().first()
    if asset:
        return asset.storage_path
    # If none marked active, get latest
    res_any = await session.execute(
        select(LibraryAsset)
        .where(LibraryAsset.category == category)
        .order_by(LibraryAsset.created_at.desc())
    )
    asset_any = res_any.scalars().first()
    if asset_any:
        return asset_any.storage_path
    raise ValueError(f"Musiqa kutubxonasida '{category}' toifasi uchun faol trek topilmadi!")

async def process_single_order(order_id: str):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        order = res.scalar_one_or_none()
        if not order:
            logger.warning(f"Order {order_id} not found.")
            return

        if order.status not in ["queued", "review_required"]:
            logger.info(f"Order {order_id} is in status '{order.status}', skipping.")
            return

        start_time = time.time()
        logger.info(f"Starting processing for order {order_id} (User: {order.user_id})...")

        try:
            # Stage 1: Transcription
            order.status = "transcribing"
            await session.commit()

            speech_recognizer = get_speech_recognizer()
            transcription = await speech_recognizer.transcribe(order.original_recording_path, language="uz")
            order.transcription_text = transcription.full_text
            await session.commit()

            # Stage 2: Stage Analysis
            order.status = "analysing"
            await session.commit()

            analyzer = get_conversation_analyzer()
            analysis = await analyzer.analyze_stages(transcription.segments, transcription.duration_seconds)

            # Store EditDecision
            edit_decision = EditDecision(
                order_id=order.id,
                language=analysis.language,
                wishes_start_seconds=analysis.wishes_start_seconds,
                call_ending_start_seconds=analysis.call_ending_start_seconds,
                wishes_confidence=analysis.wishes_confidence,
                call_ending_confidence=analysis.call_ending_confidence,
                overall_confidence=analysis.overall_confidence,
                warnings=json.dumps(analysis.warnings, ensure_ascii=False),
                transcript_segments_json=json.dumps(analysis.transcript_segments, ensure_ascii=False)
            )
            session.add(edit_decision)
            await session.commit()

            # Stage 3: Resolve Admin Library Tracks (Customer selection takes priority over active default)
            intro_path = await get_active_asset_path("number_call", session)

            starter_path = None
            if order.custom_starter_track_id:
                res_starter = await session.execute(select(LibraryAsset).where(LibraryAsset.id == order.custom_starter_track_id))
                cust_starter = res_starter.scalar_one_or_none()
                if cust_starter and os.path.exists(cust_starter.storage_path):
                    starter_path = cust_starter.storage_path
            if not starter_path:
                starter_path = await get_active_asset_path("starter", session)

            wishes_path = None
            if order.custom_wishes_track_id:
                res_wishes = await session.execute(select(LibraryAsset).where(LibraryAsset.id == order.custom_wishes_track_id))
                cust_wishes = res_wishes.scalar_one_or_none()
                if cust_wishes and os.path.exists(cust_wishes.storage_path):
                    wishes_path = cust_wishes.storage_path
            if not wishes_path:
                wishes_path = await get_active_asset_path("wishes", session)

            ending_path = None
            if order.custom_ending_track_id:
                res_ending = await session.execute(select(LibraryAsset).where(LibraryAsset.id == order.custom_ending_track_id))
                cust_ending = res_ending.scalar_one_or_none()
                if cust_ending and os.path.exists(cust_ending.storage_path):
                    ending_path = cust_ending.storage_path
            if not ending_path:
                ending_path = await get_active_asset_path("call_ending", session)

            # Stage 4: Render Production
            order.status = "rendering"
            await session.commit()

            # Determine final timing: customer custom timing takes priority over automated analysis
            if order.custom_wishes_start_seconds is not None and order.custom_wishes_start_seconds > 0:
                final_wishes_start = float(order.custom_wishes_start_seconds)
            else:
                final_wishes_start = float(analysis.wishes_start_seconds)

            if order.custom_call_ending_seconds is not None and order.custom_call_ending_seconds > final_wishes_start:
                final_ending_start = float(order.custom_call_ending_seconds)
            else:
                final_ending_start = float(analysis.call_ending_start_seconds)

            render_res = audio_renderer.render_production(
                order_id=order.id,
                original_recording_path=order.original_recording_path,
                special_music_path=order.special_music_path,
                number_call_path=intro_path,
                starter_music_path=starter_path,
                wishes_music_path=wishes_path,
                call_ending_path=ending_path,
                wishes_start_seconds=final_wishes_start,
                call_ending_start_seconds=final_ending_start,
                music_volume_db=-18.0
            )

            order.output_audio_path = render_res["output_path"]
            order.output_audio_duration = render_res["duration_seconds"]
            edit_decision.render_params_json = json.dumps(render_res["render_params"], ensure_ascii=False)

            # Cost & Resource Metrics Calculation (AT-15)
            trans_mins = round(transcription.duration_seconds / 60.0, 3)
            order.transcription_minutes = trans_mins
            order.transcription_cost_usd = round(trans_mins * 0.016, 4) if getattr(settings, "SPEECH_PROVIDER", "") == "google_chirp" else 0.0
            order.analysis_cost_usd = 0.0003 if getattr(settings, "ANALYSIS_PROVIDER", "") == "openai" else 0.0

            # Calculate total storage size in MB
            storage_bytes = 0
            for fpath in [order.original_recording_path, order.special_music_path, order.output_audio_path]:
                if fpath and os.path.exists(fpath):
                    storage_bytes += os.path.getsize(fpath)
            order.storage_mb = round(storage_bytes / (1024 * 1024), 2)

            await session.commit()

            # Stage 5: Telegram Delivery
            title_text = f"🏷️ *Nomi:* {order.audio_title}\n" if (order.audio_title and order.audio_title.strip()) else ""
            caption = (
                f"🎉 *Sizning tabrik audio montajingiz tayyor!*\n\n"
                f"{title_text}"
                f"🆔 Buyurtma: `#{order.id[:8]}`\n"
                f"⏱ Davomiyligi: {round(order.output_audio_duration, 1)} soniya\n\n"
                f"Tug'ilgan kun egasini chiroyli tabriklashingizda omad tilaymiz! 🎂🎶"
            )

            try:
                msg = await send_delivery_audio(
                    chat_id=order.user_id,
                    audio_path=order.output_audio_path,
                    caption=caption,
                    title=order.audio_title if (order.audio_title and order.audio_title.strip()) else f"Vivern MC - #{order.id[:8]}"
                )
                if msg:
                    order.delivered_to_telegram = True
                    order.telegram_message_id = msg.message_id
            except Exception as tg_err:
                logger.error(f"Telegram delivery error for user {order.user_id}: {tg_err}")
                # We do not fail the order if file is rendered; deliver flag remains False

            # Update User trial count
            if order.is_free_trial:
                res_user = await session.execute(select(User).where(User.id == order.user_id))
                u = res_user.scalar_one_or_none()
                if u:
                    u.trial_count += 1

            order.status = "completed"
            order.completed_at = datetime.utcnow()
            order.processing_time_seconds = round(time.time() - start_time, 2)
            await session.commit()
            logger.info(f"Order {order_id} successfully completed in {order.processing_time_seconds}s!")

        except Exception as e:
            logger.exception(f"Order {order_id} failed: {e}")
            order.status = "failed"
            order.error_message = str(e)
            await session.commit()

async def order_worker_loop():
    logger.info("Order background worker started.")
    while True:
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Order.id).where(Order.status == "queued").order_by(Order.created_at.asc()).limit(1)
                )
                order_id = res.scalar_one_or_none()

            if order_id:
                await process_single_order(order_id)
            else:
                await asyncio.sleep(2)
        except Exception as err:
            logger.error(f"Worker loop error: {err}")
            await asyncio.sleep(5)
