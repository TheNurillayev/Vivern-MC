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
