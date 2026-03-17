"""
handlers/settings.py — обработчики настроек пользователя
Меню: цвет фона, цвет эмодзи, разрешение, формат, медиа-фон, заметки, предпросмотр, сброс
"""
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from config import CONVERSION_PRICE
from database import db_get_settings, db_set_setting_field, db_get_user, db_log_conversion
from states import SettingsStates
from keyboards import (
    kb_main_reply, kb_settings, kb_color_reset, kb_resolution,
    kb_format, kb_back,
)
from image_processor import is_valid_hex

router = Router()
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ОТКРЫТЬ НАСТРОЙКИ
# ─────────────────────────────────────────────
@router.message(F.text == "⚙️ Настройки")
async def show_settings(msg: Message, state: FSMContext):
    await state.clear()
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        "⚙️ <b>Настройки генерации</b>\n\n"
        "Выберите параметр для изменения:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )


# ─────────────────────────────────────────────
#  ЦВЕТ ФОНА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:bg_color")
async def cb_bg_color(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_bg_color)
    await call.message.edit_text(
        "🌑 <b>Цвет фона</b>\n\n"
        "Введите HEX-цвет фона, например:\n"
        "<code>#1a1a2e</code>  <code>#0d0d0d</code>  <code>#2c003e</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_color_reset("s:back", "s:bg_color_reset")
    )
    await call.answer()


@router.callback_query(F.data == "s:bg_color_reset")
async def cb_bg_color_reset(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db_set_setting_field(call.from_user.id, "bg_color", "#1a1a2e")
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "⚙️ <b>Настройки генерации</b>\n\nЦвет фона сброшен.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer("✔ Сброшено")


@router.message(SettingsStates.waiting_bg_color)
async def receive_bg_color(msg: Message, state: FSMContext):
    color = msg.text.strip()
    if not is_valid_hex(color):
        await msg.answer("❌ Неверный формат. Введите HEX цвет: <code>#RRGGBB</code>",
                         parse_mode=ParseMode.HTML)
        return
    await state.clear()
    db_set_setting_field(msg.from_user.id, "bg_color", color)
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        f"✔ Цвет фона установлен: <code>{color}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )


# ─────────────────────────────────────────────
#  ЦВЕТ ЭМОДЗИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:emoji_color")
async def cb_emoji_color(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_emoji_color)
    await call.message.edit_text(
        "🌈 <b>Цвет эмодзи (перекраска)</b>\n\n"
        "Введите HEX-цвет для умной перекраски:\n"
        "<code>#ff0000</code>  <code>#00ff88</code>  <code>#7b2fff</code>\n\n"
        "⚠️ Используется HSV-метод: тени и блики сохраняются.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_color_reset("s:back", "s:emoji_color_reset")
    )
    await call.answer()


@router.callback_query(F.data == "s:emoji_color_reset")
async def cb_emoji_color_reset(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db_set_setting_field(call.from_user.id, "emoji_color", "")
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "⚙️ <b>Настройки генерации</b>\n\nПерекраска отключена.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer("✔ Сброшено")


@router.message(SettingsStates.waiting_emoji_color)
async def receive_emoji_color(msg: Message, state: FSMContext):
    color = msg.text.strip()
    if not is_valid_hex(color):
        await msg.answer("❌ Неверный формат. Введите HEX: <code>#RRGGBB</code>",
                         parse_mode=ParseMode.HTML)
        return
    await state.clear()
    db_set_setting_field(msg.from_user.id, "emoji_color", color)
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        f"✔ Цвет эмодзи: <code>{color}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )


# ─────────────────────────────────────────────
#  РАЗРЕШЕНИЕ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:resolution")
async def cb_resolution(call: CallbackQuery, state: FSMContext):
    await state.clear()
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "📐 <b>Разрешение</b>\n\nВыберите разрешение вывода:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_resolution(s.get("resolution", "1920x530"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("res:"))
async def cb_set_resolution(call: CallbackQuery):
    res = call.data.split(":", 1)[1]
    db_set_setting_field(call.from_user.id, "resolution", res)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        f"✔ Разрешение: <b>{res}</b>\n\n⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer(f"✔ {res}")


# ─────────────────────────────────────────────
#  ФОРМАТ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:format")
async def cb_format(call: CallbackQuery):
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "🎞 <b>Формат вывода</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_format(s.get("out_format", "GIF"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("fmt:"))
async def cb_set_format(call: CallbackQuery):
    fmt = call.data.split(":", 1)[1]
    db_set_setting_field(call.from_user.id, "out_format", fmt)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        f"✔ Формат: <b>{fmt}</b>\n\n⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer(f"✔ {fmt}")


# ─────────────────────────────────────────────
#  КАСТОМНАЯ МЕДИА-ПОДЛОЖКА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:custom_media")
async def cb_custom_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_custom_media)
    s = db_get_settings(call.from_user.id)
    has_media = "✔ задана" if s.get("custom_media") else "не задана"
    await call.message.edit_text(
        f"🖼 <b>Медиа-фон</b>\n\n"
        f"Текущая: <b>{has_media}</b>\n\n"
        f"Отправьте изображение, которое будет использоваться как фон.\n"
        f"(поддерживаются JPG, PNG, WebP)",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_color_reset("s:back", "s:custom_media_reset")
    )
    await call.answer()


@router.callback_query(F.data == "s:custom_media_reset")
async def cb_custom_media_reset(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db_set_setting_field(call.from_user.id, "custom_media", None)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "✔ Медиа-фон удалён.\n\n⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer("✔ Удалено")


@router.message(SettingsStates.waiting_custom_media, F.photo | F.document)
async def receive_custom_media(msg: Message, state: FSMContext, bot: Bot):
    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image"):
        file_id = msg.document.file_id

    if not file_id:
        await msg.answer("❌ Отправьте изображение (JPG/PNG/WebP)")
        return

    await state.clear()
    db_set_setting_field(msg.from_user.id, "custom_media", file_id)
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        "✔ Медиа-фон установлен!",
        reply_markup=kb_settings(s)
    )


@router.message(SettingsStates.waiting_custom_media)
async def custom_media_wrong(msg: Message):
    await msg.answer("❌ Отправьте изображение (JPG/PNG/WebP)")


# ─────────────────────────────────────────────
#  ЗАМЕТКИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:notes")
async def cb_notes(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_notes)
    s = db_get_settings(call.from_user.id)
    current = s.get("notes", "") or "—"
    await call.message.edit_text(
        f"📝 <b>Заметки</b>\n\n"
        f"Текущее: <b>{current}</b>\n\n"
        f"Отправьте текст заметки (будет отображаться на изображении).\n"
        f"Отправьте «-» чтобы удалить.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_color_reset("s:back", "s:notes_reset")
    )
    await call.answer()


@router.callback_query(F.data == "s:notes_reset")
async def cb_notes_reset(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db_set_setting_field(call.from_user.id, "notes", "")
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "✔ Заметки удалены.\n\n⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer("✔ Удалено")


@router.message(SettingsStates.waiting_notes)
async def receive_notes(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "-":
        text = ""
    await state.clear()
    db_set_setting_field(msg.from_user.id, "notes", text[:200])
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        f"✔ Заметки {'удалены' if not text else 'установлены'}: <b>{text or '—'}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )


# ─────────────────────────────────────────────
#  СБРОС ВСЕХ НАСТРОЕК
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:reset")
async def cb_reset_settings(call: CallbackQuery, state: FSMContext):
    await state.clear()
    from database import _db_upsert_settings
    defaults = {
        "bg_color": "#1a1a2e", "emoji_color": "", "resolution": "1920x530",
        "out_format": "GIF", "custom_media": None, "notes": "",
        "wm_text": "", "wm_font": "default", "wm_color": "#ffffff",
        "wm_position": "bottom_right", "wm_opacity": 0.7,
    }
    _db_upsert_settings(call.from_user.id, defaults)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "🔄 Все настройки сброшены.\n\n⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer("✔ Сброшено")


# ─────────────────────────────────────────────
#  НАЗАД К НАСТРОЙКАМ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:back")
async def cb_settings_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "⚙️ <b>Настройки генерации</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
    await call.answer()


# ─────────────────────────────────────────────
#  ЗАКРЫТЬ НАСТРОЙКИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:close")
async def cb_settings_close(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.answer()


# ─────────────────────────────────────────────
#  КОМАНДА /settings
# ─────────────────────────────────────────────
from aiogram.filters import Command

@router.message(Command("settings"))
async def cmd_settings(msg: Message, state: FSMContext):
    await state.clear()
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        "⚙️ <b>Настройки генерации</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_settings(s)
    )
