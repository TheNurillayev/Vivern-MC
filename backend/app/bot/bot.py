import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    FSInputFile
)
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.user import User
from sqlalchemy import select

logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

async def register_or_update_telegram_user(tg_user: types.User):
    """Permanently persist any Telegram user who interacts with the bot into the database."""
    if not tg_user:
        return
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(User).where(User.id == tg_user.id))
            user = res.scalar_one_or_none()
            is_admin = tg_user.id in settings.admin_ids
            if not user:
                user = User(
                    id=tg_user.id,
                    first_name=tg_user.first_name or "",
                    last_name=tg_user.last_name or "",
                    username=tg_user.username or "",
                    language_code="uz",
                    trial_count=0,
                    is_admin=is_admin
                )
                session.add(user)
                logger.info(f"Registered new Telegram user {tg_user.id} ({tg_user.first_name}) in database.")
            else:
                user.first_name = tg_user.first_name or ""
                user.last_name = tg_user.last_name or ""
                if tg_user.username:
                    user.username = tg_user.username
                user.is_admin = is_admin
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting user {tg_user.id}: {e}")

@dp.message.outer_middleware()
async def user_tracking_middleware(handler, event: types.Message, data):
    if event.from_user:
        await register_or_update_telegram_user(event.from_user)
    return await handler(event, data)

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    if message.from_user:
        await register_or_update_telegram_user(message.from_user)
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Foydalanuvchi"
    is_admin = user_id in settings.admin_ids

    # Set persistent chat menu button to launch the Mini App if HTTPS configured
    is_https = settings.SERVER_PUBLIC_URL.startswith("https://")
    if is_https:
        try:
            await bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="🎵 Vivern MC",
                    web_app=WebAppInfo(url=settings.SERVER_PUBLIC_URL)
                )
            )
        except Exception as e:
            logger.warning(f"Could not set chat menu button: {e}")

    # Build keyboard button if valid public URL
    kb = None
    if is_https:
        btn = InlineKeyboardButton(
            text="🚀 Mini App-ni ochish",
            web_app=WebAppInfo(url=settings.SERVER_PUBLIC_URL)
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])

    admin_badge = "👑 *Administrator*" if is_admin else "👤 *Foydalanuvchi*"

    welcome_text = (
        f"👋 Assalomu alaykum, *{first_name}*!\n\n"
        f"🎉 *Vivern MC* ovoz studiyasiga xush kelibsiz!\n"
        f"Bu yerda siz tug'ilgan kun suhbatlari yozuvini professional ovoz va musiqa bilan "
        f"avtomatlashtirilgan tarzda tayyorlashingiz mumkin.\n\n"
        f"📌 Sizning maqomingiz: {admin_badge}\n"
        f"🆔 Telegram ID: `{user_id}`\n\n"
    )

    if is_https:
        welcome_text += "Buyurtma berish uchun quyidagi tugmani bosing:"
    else:
        welcome_text += f"🌐 Mini App-ni ochish uchun brauzeringizda ushbu havolaga kiring:\n`{settings.SERVER_PUBLIC_URL}`"

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=kb)

@dp.message(Command("admin"))
async def handle_admin(message: types.Message):
    user_id = message.from_user.id
    if user_id not in settings.admin_ids:
        await message.answer("⛔ Kechirasiz, siz administrator emassiz.")
        return

    admin_url = f"{settings.SERVER_PUBLIC_URL}/admin.html"
    is_https = settings.SERVER_PUBLIC_URL.startswith("https://")
    kb = None
    if is_https:
        admin_btn = InlineKeyboardButton(
            text="⚙️ Admin Panelni Ochish",
            web_app=WebAppInfo(url=admin_url)
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[admin_btn]])

    admin_text = (
        "👑 *Vivern MC Administrator Paneli*\n\n"
        "Siz musiqa kutubxonasini boshqarishingiz, buyurtmalarni kuzatishingiz "
        "va audio parametrlarni sozlashingiz mumkin.\n\n"
    )
    if not is_https:
        admin_text += f"⚙️ Admin panel havolasi:\n`{admin_url}`"

    await message.answer(
        admin_text,
        parse_mode="Markdown",
        reply_markup=kb
    )

async def send_delivery_audio(chat_id: int, audio_path: str, caption: str, title: str = None):
    """Deliver completed audio production directly into customer's chat."""
    audio_file = FSInputFile(audio_path)
    kwargs = {
        "chat_id": chat_id,
        "audio": audio_file,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if title:
        kwargs["title"] = title
    return await bot.send_audio(**kwargs)

async def send_receipt_to_admins(
    file_path: str,
    caption: str,
    is_image: bool = True,
    user_id: int = 0,
    coins: int = 10
):
    """Deliver payment receipt directly into administrators' chats with Cancel, Confirm, Admin Panel buttons."""
    doc = FSInputFile(file_path)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Cancel", callback_data=f"rcpt:cancel:{user_id}:{coins}"),
                InlineKeyboardButton(text="Confirm", callback_data=f"rcpt:confirm:{user_id}:{coins}"),
                InlineKeyboardButton(text="Admin Panel", callback_data=f"rcpt:ap:{user_id}:{coins}")
            ]
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            if is_image:
                await bot.send_photo(chat_id=admin_id, photo=doc, caption=caption, parse_mode="Markdown", reply_markup=kb)
            else:
                await bot.send_document(chat_id=admin_id, document=doc, caption=caption, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Error sending receipt to admin {admin_id}: {e}")

@dp.callback_query(lambda c: c.data and c.data.startswith("rcpt:"))
async def handle_receipt_callback(callback: types.CallbackQuery):
    admin_id = callback.from_user.id
    if admin_id not in settings.admin_ids:
        await callback.answer("⛔ Siz administrator emassiz!", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Noto'g'ri so'rov", show_alert=True)
        return

    action = parts[1]        # "cancel", "confirm", "ap"
    target_user_id = int(parts[2])
    coins = int(parts[3])

    if action == "cancel":
        # 3 buttons disappear, "Canceled" appears
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Canceled", callback_data="none")]
            ]
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=cancel_kb)
        except Exception as e:
            logger.warning(f"Could not edit reply markup on cancel: {e}")

        # Notify user
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text="❌ Siz yuborgan to'lov cheki ma'muriyat tomonidan bekor qilindi.\nAgar xatolik deb hisoblasangiz, @TheNurillayev bilan bog'laning."
            )
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} of cancellation: {e}")

        await callback.answer("Foydalanuvchi talabi bekor qilindi (Canceled)")

    elif action == "confirm":
        # Automatically add coins to user in DB
        new_coins = coins
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(User).where(User.id == target_user_id))
                target_user = res.scalar_one_or_none()
                if target_user:
                    target_user.coins = max(0, (target_user.coins or 0) + coins)
                    await session.commit()
                    new_coins = target_user.coins
        except Exception as e:
            logger.error(f"Error adding coins to user {target_user_id}: {e}")

        # 3 buttons disappear, "Confirmed" appears
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Confirmed", callback_data="none")]
            ]
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=confirm_kb)
        except Exception as e:
            logger.warning(f"Could not edit reply markup on confirm: {e}")

        # Notify user
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 *To'lovingiz tasdiqlandi!*\n\n"
                    f"🪙 Hisobingizga *+{coins} Tanga* muvaffaqiyatli qo'shildi!\n"
                    f"Jami balansingiz: *{new_coins} Tanga*.\n\n"
                    f"Endi bemalol professional audio montaj buyurtma berishingiz mumkin."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} of confirmation: {e}")

        await callback.answer(f"Tasdiqlandi! +{coins} Tanga foydalanuvchiga qo'shildi.")

    elif action == "ap":
        # 3 buttons disappear, "Confirmed by A.P." appears
        admin_url = f"{settings.SERVER_PUBLIC_URL}/admin.html?user_id={target_user_id}"
        ap_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Confirmed by A.P.", callback_data="none")]
            ]
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=ap_kb)
        except Exception as e:
            logger.warning(f"Could not edit reply markup on AP: {e}")

        # Send direct navigation message with WebApp and direct URL
        direct_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👤 Foydalanuvchi profilini ochish", web_app=WebAppInfo(url=admin_url))],
                [InlineKeyboardButton(text="🌐 Brauzerda ochish", url=admin_url)]
            ]
        )
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                f"👤 *Foydalanuvchi ID:* `{target_user_id}`\n\n"
                f"Ushbu foydalanuvchining profiliga to'g'ridan-to'g'ri o'tib, tangalarni qo'lda qo'shish uchun quyidagi tugmani bosing:"
            ),
            reply_markup=direct_kb,
            parse_mode="Markdown"
        )
        await callback.answer("Admin panelga yo'naltirilmoqda...")

@dp.callback_query(lambda c: c.data == "none")
async def handle_noop_callback(callback: types.CallbackQuery):
    await callback.answer()
