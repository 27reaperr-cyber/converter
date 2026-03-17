"""
handlers/media_handler.py — приём и обработка эмодзи / стикеров / изображений

Пайплайн:
  1. Пользователь присылает emoji-текст / стикер / фото
  2. FSM сохраняет медиа, показывает подтверждение + цену
  3. После подтверждения — проверяем баланс
  4. Списываем 5₽, генерируем вывод, отправляем
  5. Предпросмотр — бесплатно (1 кадр PNG)
"""

import io
import os
import logging
import asyncio
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    BufferedInputFile,
)
from aiogram.enums import ParseMode

from config import CONVERSION_PRICE, PREVIEW_FREE, TEMP_DIR
from database import (
    db_get_settings, db_get_user, db_get_balance,
    db_update_balance, db_log_conversion,
    db_get_or_create_user,
)
from states import MediaStates
from keyboards import kb_confirm_convert, kb_main_reply, kb_topup, kb_settings
from image_processor import process_input_to_image
from gif_generator import render_output

router = Router()
log = logging.getLogger(__name__)

# Убедимся что temp-директория есть
os.makedirs(TEMP_DIR, exist_ok=True)


# ─────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────

def _is_emoji(text: str) -> bool:
    """Проверяем что текст содержит emoji (не обычные буквы)"""
    if not text or len(text) > 10:
        return False
    for char in text:
        cp = ord(char)
        # Диапазоны emoji
        if (0x1F300 <= cp <= 0x1FAFF or  # разные эмодзи
                0x2600 <= cp <= 0x27BF or   # символы
                0xFE00 <= cp <= 0xFE0F or   # вариационные селекторы
                0x200D == cp or              # ZWJ
                0x1F004 <= cp <= 0x1F0CF):
            continue
        if char.isalpha() or char.isdigit():
            return False
    return any(ord(c) > 0x2000 for c in text)


async def _download_file(bot: Bot, file_id: str) -> bytes:
    """Скачивает файл из Telegram в bytes"""
    file = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    return buf.getvalue()


async def _load_custom_bg(bot: Bot, file_id: str) -> Optional:
    """Загружает кастомный фон из file_id"""
    try:
        data = await _download_file(bot, file_id)
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        return img
    except Exception as e:
        log.warning(f"Custom BG load failed: {e}")
        return None


def _format_settings_brief(s: dict) -> str:
    ec = s.get("emoji_color", "") or "нет"
    wm = s.get("wm_text", "") or "нет"
    return (
        f"◦ Формат: <b>{s.get('out_format','GIF')}</b>  "
        f"◦ Разрешение: <b>{s.get('resolution','1920x530')}</b>\n"
        f"◦ Цвет фона: <code>{s.get('bg_color','#1a1a2e')}</code>  "
        f"◦ Цвет эмодзи: <code>{ec}</code>\n"
        f"◦ Вотермарка: <b>{wm[:20]}</b>"
    )


# ─────────────────────────────────────────────
#  КНОПКА "СОЗДАТЬ" → переход в режим ожидания
# ─────────────────────────────────────────────
@router.message(F.text == "🎨 Создать")
async def cmd_create(msg: Message, state: FSMContext):
    await state.set_state(MediaStates.waiting_emoji_input)
    await msg.answer(
        "🎨 <b>Режим создания</b>\n\n"
        "Отправьте:\n"
        "◦ <b>Эмодзи</b> — любой символ (🔥🌊✨💫)\n"
        "◦ <b>Стикер</b> — .webp или .tgs анимация\n"
        "◦ <b>Изображение</b> — любое фото/PNG\n\n"
        "Текущие настройки применятся автоматически.\n"
        "Предпросмотр — бесплатно! 👁",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────
#  ПРЕДПРОСМОТР ИЗ МЕНЮ НАСТРОЕК
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:preview")
async def cb_preview_from_settings(call: CallbackQuery, state: FSMContext):
    """Предпросмотр: просит пользователя ввести эмодзи"""
    await state.set_state(MediaStates.waiting_emoji_input)
    await state.update_data(preview_mode=True)
    await call.message.answer(
        "👁 <b>Предпросмотр</b>\n\n"
        "Отправьте эмодзи, стикер или изображение — "
        "получите PNG-предпросмотр бесплатно.",
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


# ─────────────────────────────────────────────
#  ПРИЁМ ЭМОДЗИ (текст)
# ─────────────────────────────────────────────
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message, state: FSMContext, bot: Bot):
    text = msg.text.strip()
    if not _is_emoji(text):
        # Если не в состоянии создания — игнорируем
        cur_state = await state.get_state()
        if cur_state != MediaStates.waiting_emoji_input:
            return
        await msg.answer(
            "❌ Не распознан как эмодзи.\n"
            "Отправьте символ эмодзи, например: 🔥 ✨ 💎",
        )
        return

    await _process_media(
        msg=msg, state=state, bot=bot,
        input_type="emoji",
        input_text=text,
        input_data=b"",
    )


# ─────────────────────────────────────────────
#  ПРИЁМ СТИКЕРА
# ─────────────────────────────────────────────
@router.message(F.sticker)
async def handle_sticker(msg: Message, state: FSMContext, bot: Bot):
    sticker = msg.sticker
    is_animated = sticker.is_animated  # .tgs
    is_video = sticker.is_video        # .webm (не поддерживается полностью)

    input_type = "sticker_tgs" if is_animated else "sticker_webp"

    # Скачиваем
    try:
        data = await _download_file(bot, sticker.file_id)
    except Exception as e:
        await msg.answer(f"❌ Не удалось скачать стикер: {e}")
        return

    await _process_media(
        msg=msg, state=state, bot=bot,
        input_type=input_type,
        input_text="",
        input_data=data,
    )


# ─────────────────────────────────────────────
#  ПРИЁМ ИЗОБРАЖЕНИЯ
# ─────────────────────────────────────────────
@router.message(F.photo | (F.document & F.document.mime_type.startswith("image")))
async def handle_image(msg: Message, state: FSMContext, bot: Bot):
    # Проверяем что мы не в режиме ожидания кастомного фона
    cur_state = await state.get_state()
    from states import SettingsStates
    if cur_state == SettingsStates.waiting_custom_media:
        return  # передаём settings.py

    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.document:
        file_id = msg.document.file_id

    try:
        data = await _download_file(bot, file_id)
    except Exception as e:
        await msg.answer(f"❌ Не удалось скачать изображение: {e}")
        return

    await _process_media(
        msg=msg, state=state, bot=bot,
        input_type="image",
        input_text="",
        input_data=data,
    )


# ─────────────────────────────────────────────
#  ОБЩАЯ ЛОГИКА: ПОДТВЕРЖДЕНИЕ
# ─────────────────────────────────────────────
async def _process_media(
    msg: Message,
    state: FSMContext,
    bot: Bot,
    input_type: str,
    input_text: str,
    input_data: bytes,
):
    """Сохраняет данные в FSM, показывает подтверждение"""
    db_get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )

    user = db_get_user(msg.from_user.id)
    if user and user["is_banned"]:
        await msg.answer("🚫 Вы заблокированы.")
        return

    fsm_data = await state.get_data()
    preview_mode = fsm_data.get("preview_mode", False)

    # Сохраняем данные
    await state.update_data(
        input_type=input_type,
        input_text=input_text,
        input_data_hex=input_data.hex() if input_data else "",
    )

    s = db_get_settings(msg.from_user.id)
    balance = db_get_balance(msg.from_user.id)
    fmt = s.get("out_format", "GIF")

    if preview_mode:
        # Предпросмотр бесплатен
        await state.update_data(confirmed=True, preview_only=True)
        await _do_generate(msg, state, bot)
        return

    # Показываем подтверждение
    can_afford = balance >= CONVERSION_PRICE
    balance_str = f"Баланс: <b>{balance:.2f}₽</b>"
    if not can_afford:
        deficit = CONVERSION_PRICE - balance
        topup_hint = f"\n\n⚠️ Недостаточно средств. Нужно пополнить на <b>{deficit:.0f}₽</b>."
    else:
        topup_hint = ""

    settings_line = _format_settings_brief(s)

    await msg.answer(
        f"🎨 <b>Подтверждение конвертации</b>\n\n"
        f"{settings_line}\n\n"
        f"{balance_str}"
        f"{topup_hint}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_confirm_convert(fmt, CONVERSION_PRICE)
        if can_afford else kb_topup(),
    )


# ─────────────────────────────────────────────
#  ПОДТВЕРЖДЕНИЕ / ОТМЕНА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "convert:confirm")
async def cb_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    balance = db_get_balance(call.from_user.id)
    if balance < CONVERSION_PRICE:
        await call.answer("❌ Недостаточно средств!", show_alert=True)
        return

    await call.message.edit_text("⏳ Генерирую…")
    await call.answer()

    await state.update_data(confirmed=True, preview_only=False)
    await _do_generate(call.message, state, bot, user_id=call.from_user.id)


@router.callback_query(F.data == "convert:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.", reply_markup=None)
    await call.answer()


# ─────────────────────────────────────────────
#  ГЕНЕРАЦИЯ
# ─────────────────────────────────────────────
async def _do_generate(
    msg: Message,
    state: FSMContext,
    bot: Bot,
    user_id: int = None,
):
    """Производит генерацию и отправляет результат"""
    if user_id is None:
        user_id = msg.chat.id

    data = await state.get_data()
    preview_only = data.get("preview_only", False)
    input_type   = data.get("input_type", "emoji")
    input_text   = data.get("input_text", "")
    input_hex    = data.get("input_data_hex", "")
    input_data   = bytes.fromhex(input_hex) if input_hex else b""

    s = db_get_settings(user_id)

    # ── Загружаем кастомный фон ───────────────
    custom_bg = None
    if s.get("custom_media"):
        custom_bg = await _load_custom_bg(bot, s["custom_media"])

    # ── Обрабатываем ввод в PIL Image ────────
    try:
        emoji_img = await process_input_to_image(
            input_data=input_data,
            input_type=input_type,
            input_text=input_text,
            settings=s,
        )
    except Exception as e:
        log.exception("process_input_to_image failed")
        await msg.answer(f"❌ Ошибка обработки изображения:\n<code>{e}</code>",
                         parse_mode=ParseMode.HTML)
        await state.clear()
        return

    if emoji_img is None:
        await msg.answer("❌ Не удалось получить изображение. Попробуйте другой эмодзи/стикер.")
        await state.clear()
        return

    # ── Рендер вывода ─────────────────────────
    try:
        file_bytes, mime_type = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: render_output(emoji_img, s, custom_bg, preview_only=preview_only)
        )
    except Exception as e:
        log.exception("render_output failed")
        await msg.answer(f"❌ Ошибка генерации:\n<code>{e}</code>",
                         parse_mode=ParseMode.HTML)
        await state.clear()
        return

    # ── Списываем баланс (не для предпросмотра) ─
    if not preview_only:
        db_update_balance(user_id, -CONVERSION_PRICE)
        db_log_conversion(user_id, s.get("out_format", "GIF"), CONVERSION_PRICE)

    # ── Отправляем файл ───────────────────────
    fmt = s.get("out_format", "GIF")
    ext_map = {"GIF": "gif", "PNG": "png", "MP4": "mp4"}
    ext = ext_map.get(fmt if not preview_only else "PNG", "gif")
    filename = f"output.{ext}"

    inp_file = BufferedInputFile(file_bytes, filename=filename)

    caption = "👁 <b>Предпросмотр</b>" if preview_only else f"✨ <b>{fmt} готов!</b>"
    if not preview_only:
        balance_new = db_get_balance(user_id)
        caption += f"\n💰 Баланс: <b>{balance_new:.2f}₽</b>"

    try:
        if ext == "gif":
            await bot.send_animation(
                chat_id=msg.chat.id,
                animation=inp_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        elif ext == "mp4":
            await bot.send_video(
                chat_id=msg.chat.id,
                video=inp_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.send_photo(
                chat_id=msg.chat.id,
                photo=inp_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        log.exception("File send failed")
        await msg.answer(f"❌ Не удалось отправить файл: {e}")

    await state.clear()


# ─────────────────────────────────────────────
#  КАСТОМНЫЕ ЭМОДЗИ — использование
# ─────────────────────────────────────────────
@router.message(F.text == "💎 Эмодзи")
async def show_custom_emoji(msg: Message):
    from database import db_get_custom_emoji, db_count_custom_emoji
    from keyboards import kb_custom_emoji_list

    total = db_count_custom_emoji()
    if total == 0:
        await msg.answer(
            "💎 <b>Кастомные эмодзи</b>\n\n"
            "Пока нет кастомных эмодзи.\n"
            "Администратор может добавить их в панели управления.",
            parse_mode=ParseMode.HTML,
        )
        return

    emojis = db_get_custom_emoji(limit=10, offset=0)
    await msg.answer(
        f"💎 <b>Кастомные эмодзи</b>\n\n"
        f"Доступно: <b>{total}</b> шт.\n"
        f"Выберите для использования:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_custom_emoji_list(emojis, page=0, total=total)
    )


@router.callback_query(F.data.startswith("emoji_page:"))
async def cb_emoji_page(call: CallbackQuery):
    from database import db_get_custom_emoji, db_count_custom_emoji
    from keyboards import kb_custom_emoji_list

    page = int(call.data.split(":")[1])
    total = db_count_custom_emoji()
    emojis = db_get_custom_emoji(limit=10, offset=page * 10)
    await call.message.edit_reply_markup(
        reply_markup=kb_custom_emoji_list(emojis, page=page, total=total)
    )
    await call.answer()


@router.callback_query(F.data.startswith("use_emoji:"))
async def cb_use_custom_emoji(call: CallbackQuery, state: FSMContext, bot: Bot):
    from database import db_get_custom_emoji
    emoji_id = int(call.data.split(":")[1])

    # Ищем в БД
    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM custom_emoji WHERE id=?", (emoji_id,)
        ).fetchone()

    if not row:
        await call.answer("❌ Эмодзи не найден", show_alert=True)
        return

    file_id   = row["file_id"]
    file_type = row["file_type"]

    try:
        data = await _download_file(bot, file_id)
    except Exception as e:
        await call.answer(f"❌ Ошибка загрузки: {e}", show_alert=True)
        return

    input_type = "sticker_webp" if file_type == "sticker" else "image"

    await call.answer("✔ Выбрано!")
    await _process_media(
        msg=call.message, state=state, bot=bot,
        input_type=input_type,
        input_text="",
        input_data=data,
    )


@router.callback_query(F.data == "emoji:back")
async def cb_emoji_back(call: CallbackQuery):
    await call.message.delete()
    await call.answer()
