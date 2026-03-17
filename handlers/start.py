"""
handlers/start.py — команды /start, /help, главное меню, профиль, о боте
"""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from config import BOT_USERNAME, CONVERSION_PRICE, is_admin
from database import (
    db_get_or_create_user, db_get_user, db_get_balance,
    db_add_referral, db_count_referrals, db_get_settings,
)
from keyboards import kb_main_reply, kb_back

router = Router()
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  /start [ref_XXXX]
# ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()

    # Обработка реферальной ссылки
    referrer_id = None
    args = msg.text.split(maxsplit=1)
    if len(args) > 1:
        ref_arg = args[1]
        if ref_arg.startswith("ref_"):
            try:
                referrer_id = int(ref_arg[4:])
                if referrer_id == msg.from_user.id:
                    referrer_id = None
            except ValueError:
                pass

    user = db_get_or_create_user(
        telegram_id=msg.from_user.id,
        username=msg.from_user.username or "",
        full_name=msg.from_user.full_name or "",
        referrer_id=referrer_id,
    )

    # Записываем реферал если пользователь новый
    if referrer_id and user:
        db_add_referral(referrer_id, msg.from_user.id)

    if user and user["is_banned"]:
        await msg.answer("🚫 Вы заблокированы в этом боте.")
        return

    name = msg.from_user.first_name or "пользователь"
    text = (
        f"✦ <b>Привет, {name}!</b>\n\n"
        f"Этот бот генерирует <b>GIF / PNG / MP4</b> из эмодзи и стикеров "
        f"с умной перекраской, вотермаркой и кастомным фоном.\n\n"
        f"<b>Как использовать:</b>\n"
        f"◦ Отправь <b>эмодзи</b> (например 🔥) — получи анимацию\n"
        f"◦ Отправь <b>стикер</b> — перекрась в любой цвет\n"
        f"◦ Настрой фон, шрифт, вотермарку в <b>⚙️ Настройках</b>\n\n"
        f"💲 Стоимость: <b>{CONVERSION_PRICE:.0f}₽</b> / конвертация\n"
        f"👁 Предпросмотр — <b>бесплатно</b>"
    )
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb_main_reply())


# ─────────────────────────────────────────────
#  /help
# ─────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(msg: Message):
    text = (
        "📖 <b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/settings — настройки\n"
        "/profile — ваш профиль\n"
        "/topup — пополнить баланс\n"
        "/help — эта справка\n\n"
        "<b>Как создать GIF:</b>\n"
        "1. Отправьте эмодзи-символ (🔥✨💫 и т.д.)\n"
        "   <i>или</i> стикер / изображение\n"
        "2. Подтвердите конвертацию\n"
        "3. Получите готовый файл\n\n"
        "<b>Настройки (⚙️):</b>\n"
        "• Цвет фона / эмодзи\n"
        "• Разрешение и формат (GIF/PNG/MP4)\n"
        "• Заметки и вотермарка\n"
        "• Свой фон-изображение\n\n"
        "💎 В разделе <b>Эмодзи</b> — кастомные стикер-паки"
    )
    await msg.answer(text, parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────
#  ПРОФИЛЬ
# ─────────────────────────────────────────────
@router.message(F.text == "👤 Профиль")
@router.message(Command("profile"))
async def show_profile(msg: Message):
    user = db_get_user(msg.from_user.id)
    if not user:
        await msg.answer("Профиль не найден. Нажмите /start")
        return

    balance   = float(user["balance"])
    spent     = float(user["total_spent"])
    convers   = int(user["conversions"])
    reg_date  = user["reg_date"]
    refs      = db_count_referrals(msg.from_user.id)
    username  = f"@{user['username']}" if user["username"] else "—"

    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{msg.from_user.id}"

    text = (
        f"👤 <b>Ваш профиль</b>\n"
        f"{'─' * 22}\n"
        f"◦ Имя: <b>{user['full_name'] or '—'}</b>\n"
        f"◦ Username: <b>{username}</b>\n"
        f"◦ ID: <code>{msg.from_user.id}</code>\n"
        f"◦ Регистрация: <b>{reg_date}</b>\n\n"
        f"💰 Баланс: <b>{balance:.2f}₽</b>\n"
        f"💸 Потрачено: <b>{spent:.2f}₽</b>\n"
        f"🎞 Конвертаций: <b>{convers}</b>\n\n"
        f"👥 Рефералов: <b>{refs}</b>\n"
        f"🔗 Реф. ссылка:\n<code>{ref_link}</code>"
    )
    await msg.answer(text, parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────
#  О БОТЕ
# ─────────────────────────────────────────────
@router.message(F.text == "ℹ️ О боте")
async def show_about(msg: Message):
    text = (
        "✦ <b>О боте</b>\n\n"
        "Бот для генерации <b>GIF</b>, <b>PNG</b> и <b>MP4</b> "
        "из эмодзи и стикеров.\n\n"
        "<b>Технологии:</b>\n"
        "◦ aiogram 3.x\n"
        "◦ Pillow + NumPy — обработка изображений\n"
        "◦ Умная перекраска через HSV\n"
        "◦ imageio — генерация анимаций\n\n"
        "<b>Возможности:</b>\n"
        "◦ Перекраска с сохранением теней и объёма\n"
        "◦ 60fps GIF анимация\n"
        "◦ Кастомный фон, заметки, вотермарка\n"
        "◦ Кастомные эмодзи-паки\n"
    )
    await msg.answer(text, parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────
#  /admin
# ─────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("🚫 Нет доступа")
        return
    from keyboards import kb_admin_main
    await msg.answer(
        "🔧 <b>Панель администратора</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_main()
    )
