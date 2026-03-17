"""
handlers/watermark.py — меню настройки вотермарки
"""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from database import db_get_settings, db_set_setting_field
from states import WatermarkStates
from keyboards import kb_watermark, kb_fonts, kb_wm_position, kb_settings, kb_back
from image_processor import is_valid_hex, list_fonts

router = Router()
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ОТКРЫТЬ МЕНЮ ВОТЕРМАРКИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "s:watermark")
async def cb_watermark_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    s = db_get_settings(call.from_user.id)
    wm_text = s.get("wm_text", "")
    if not wm_text:
        hint = "\n⚠️ <i>Вотермарка не задана</i>"
    else:
        hint = f"\n✔ Текст: <b>{wm_text[:20]}</b>"

    await call.message.edit_text(
        f"💧 <b>Вотермарка</b>{hint}\n\n"
        "Настройте текст, шрифт, цвет и позицию:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )
    await call.answer()


# ─────────────────────────────────────────────
#  ТЕКСТ ВОТЕРМАРКИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wm:text")
async def cb_wm_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(WatermarkStates.waiting_text)
    s = db_get_settings(call.from_user.id)
    current = s.get("wm_text", "") or "—"
    await call.message.edit_text(
        f"✏️ <b>Текст вотермарки</b>\n\n"
        f"Текущий: <b>{current}</b>\n\n"
        f"Введите новый текст вотермарки.\n"
        f"Отправьте «-» чтобы удалить.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("s:watermark")
    )
    await call.answer()


@router.message(WatermarkStates.waiting_text)
async def receive_wm_text(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "-":
        text = ""
    await state.clear()
    db_set_setting_field(msg.from_user.id, "wm_text", text[:100])
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        f"✔ Вотермарка: {'удалена' if not text else f'<b>{text}</b>'}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )


# ─────────────────────────────────────────────
#  УДАЛИТЬ ВОТЕРМАРКУ (быстро)
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wm:clear")
async def cb_wm_clear(call: CallbackQuery, state: FSMContext):
    await state.clear()
    db_set_setting_field(call.from_user.id, "wm_text", "")
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "✔ Вотермарка удалена.\n\n💧 <b>Вотермарка</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )
    await call.answer("✔ Удалено")


# ─────────────────────────────────────────────
#  ШРИФТ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wm:font")
async def cb_wm_font(call: CallbackQuery, state: FSMContext):
    s = db_get_settings(call.from_user.id)
    fonts = list_fonts()
    await call.message.edit_text(
        "🔤 <b>Шрифт вотермарки</b>\n\nВыберите шрифт:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_fonts(fonts, s.get("wm_font", "default"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("wm_font:"))
async def cb_set_wm_font(call: CallbackQuery):
    font = call.data.split(":", 1)[1]
    db_set_setting_field(call.from_user.id, "wm_font", font)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        f"✔ Шрифт: <b>{font}</b>\n\n💧 <b>Вотермарка</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )
    await call.answer(f"✔ {font}")


# ─────────────────────────────────────────────
#  ЦВЕТ ВОТЕРМАРКИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wm:color")
async def cb_wm_color(call: CallbackQuery, state: FSMContext):
    await state.set_state(WatermarkStates.waiting_color)
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        f"🎨 <b>Цвет вотермарки</b>\n\n"
        f"Текущий: <code>{s.get('wm_color', '#ffffff')}</code>\n\n"
        "Введите HEX-цвет: <code>#ffffff</code>  <code>#ffcc00</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("s:watermark")
    )
    await call.answer()


@router.message(WatermarkStates.waiting_color)
async def receive_wm_color(msg: Message, state: FSMContext):
    color = msg.text.strip()
    if not is_valid_hex(color):
        await msg.answer("❌ Неверный формат. Введите HEX: <code>#RRGGBB</code>",
                         parse_mode=ParseMode.HTML)
        return
    await state.clear()
    db_set_setting_field(msg.from_user.id, "wm_color", color)
    s = db_get_settings(msg.from_user.id)
    await msg.answer(
        f"✔ Цвет вотермарки: <code>{color}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )


# ─────────────────────────────────────────────
#  ПОЗИЦИЯ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wm:position")
async def cb_wm_position(call: CallbackQuery):
    s = db_get_settings(call.from_user.id)
    await call.message.edit_text(
        "📍 <b>Позиция вотермарки</b>\n\nВыберите позицию:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_wm_position(s.get("wm_position", "bottom_right"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("wm_pos:"))
async def cb_set_wm_pos(call: CallbackQuery):
    pos = call.data.split(":", 1)[1]
    db_set_setting_field(call.from_user.id, "wm_position", pos)
    s = db_get_settings(call.from_user.id)
    from config import WM_POSITIONS
    label = WM_POSITIONS.get(pos, pos)
    await call.message.edit_text(
        f"✔ Позиция: <b>{label}</b>\n\n💧 <b>Вотермарка</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_watermark(s)
    )
    await call.answer(f"✔ {label}")
