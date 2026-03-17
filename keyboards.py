"""
keyboards.py — все клавиатуры бота (inline + reply)
"""
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from config import RESOLUTIONS, FORMATS, WM_POSITIONS


# ─────────────────────────────────────────────
#  ГЛАВНАЯ REPLY-КЛАВИАТУРА
# ─────────────────────────────────────────────
def kb_main_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎨 Создать"),  KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="💎 Эмодзи"),   KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="💳 Пополнить"),KeyboardButton(text="ℹ️ О боте")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или отправьте эмодзи/стикер",
    )


# ─────────────────────────────────────────────
#  ГЛАВНОЕ INLINE-МЕНЮ НАСТРОЕК
# ─────────────────────────────────────────────
def kb_settings(settings: dict) -> InlineKeyboardMarkup:
    """Меню настроек с текущими значениями"""
    fmt     = settings.get("out_format", "GIF")
    bg      = settings.get("bg_color",   "#1a1a2e")
    ec      = settings.get("emoji_color","") or "нет"
    res     = settings.get("resolution", "1920x530")
    notes   = settings.get("notes", "") or "нет"
    wm      = settings.get("wm_text", "")
    has_bg  = "✔" if settings.get("custom_media") else "✕"

    wm_label = f"💧 Вотермарка: {wm[:12]+'…' if len(wm)>12 else wm}" if wm else "💧 Вотермарка: не задана"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌑 Цвет фона: {bg}",       callback_data="s:bg_color")],
        [InlineKeyboardButton(text=f"🌈 Цвет эмодзи: {ec}",     callback_data="s:emoji_color")],
        [InlineKeyboardButton(text=f"📐 Разрешение: {res}",     callback_data="s:resolution")],
        [InlineKeyboardButton(text=f"🎞 Формат: {fmt}",          callback_data="s:format")],
        [InlineKeyboardButton(text=f"🖼 Фон-медиа: {has_bg}",   callback_data="s:custom_media")],
        [InlineKeyboardButton(text=f"📝 Заметки: {notes[:12]+'…' if len(notes)>12 else notes}", callback_data="s:notes")],
        [InlineKeyboardButton(text=wm_label,                     callback_data="s:watermark")],
        [
            InlineKeyboardButton(text="👁 Предпросмотр", callback_data="s:preview"),
            InlineKeyboardButton(text="🔄 Сброс",        callback_data="s:reset"),
        ],
        [InlineKeyboardButton(text="← Закрыть",              callback_data="s:close")],
    ])


# ─────────────────────────────────────────────
#  ЦВЕТ (возможность сбросить или ввести HEX)
# ─────────────────────────────────────────────
def kb_color_reset(back_cb: str, reset_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✕ Сбросить цвет", callback_data=reset_cb)],
        [InlineKeyboardButton(text="← Назад",          callback_data=back_cb)],
    ])


# ─────────────────────────────────────────────
#  РАЗРЕШЕНИЕ
# ─────────────────────────────────────────────
def kb_resolution(current: str) -> InlineKeyboardMarkup:
    rows = []
    for label, value in RESOLUTIONS:
        mark = "✔ " if value == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"res:{value}"
        )])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="s:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────
#  ФОРМАТ
# ─────────────────────────────────────────────
def kb_format(current: str) -> InlineKeyboardMarkup:
    btns = []
    for f in FORMATS:
        mark = "✔ " if f == current else ""
        btns.append(InlineKeyboardButton(text=f"{mark}{f}", callback_data=f"fmt:{f}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        btns,
        [InlineKeyboardButton(text="← Назад", callback_data="s:back")],
    ])


# ─────────────────────────────────────────────
#  ВОТЕРМАРКА — главное меню
# ─────────────────────────────────────────────
def kb_watermark(settings: dict) -> InlineKeyboardMarkup:
    wm_text  = settings.get("wm_text",     "")
    wm_font  = settings.get("wm_font",     "default")
    wm_color = settings.get("wm_color",    "#ffffff")
    wm_pos   = WM_POSITIONS.get(settings.get("wm_position", "bottom_right"), "↘ Низ-право")

    wm_label = wm_text[:18] + "…" if len(wm_text) > 18 else (wm_text or "не задан")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✏️ Название: {wm_label}",  callback_data="wm:text")],
        [InlineKeyboardButton(text=f"🔤 Шрифт: {wm_font}",      callback_data="wm:font")],
        [InlineKeyboardButton(text=f"🎨 Цвет: {wm_color}",      callback_data="wm:color")],
        [InlineKeyboardButton(text=f"📍 Позиция: {wm_pos}",     callback_data="wm:position")],
        [InlineKeyboardButton(text="✕ Удалить вотермарку",       callback_data="wm:clear")],
        [InlineKeyboardButton(text="← Назад",                    callback_data="s:back")],
    ])


# ─────────────────────────────────────────────
#  ШРИФТЫ ВОТЕРМАРКИ
# ─────────────────────────────────────────────
def kb_fonts(available_fonts: list, current: str) -> InlineKeyboardMarkup:
    rows = []
    for font in available_fonts:
        label = font if font != "default" else "По умолчанию"
        mark = "✔ " if font == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"wm_font:{font}"
        )])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="s:watermark")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────
#  ПОЗИЦИИ ВОТЕРМАРКИ
# ─────────────────────────────────────────────
def kb_wm_position(current: str) -> InlineKeyboardMarkup:
    rows = []
    for key, label in WM_POSITIONS.items():
        mark = "✔ " if key == current else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"wm_pos:{key}"
        )])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="s:watermark")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────
#  ПОДТВЕРЖДЕНИЕ КОНВЕРТАЦИИ
# ─────────────────────────────────────────────
def kb_confirm_convert(fmt: str, price: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Конвертировать ({fmt}) — {price:.0f}₽",
            callback_data="convert:confirm"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="convert:cancel")],
    ])


# ─────────────────────────────────────────────
#  ОПЛАТА / ПОПОЛНЕНИЕ БАЛАНСА
# ─────────────────────────────────────────────
def kb_topup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 CryptoBot (крипта)",    callback_data="pay:crypto")],
        [InlineKeyboardButton(text="🏦 Банковская карта",       callback_data="pay:card")],
        [InlineKeyboardButton(text="← Назад",                   callback_data="pay:back")],
    ])


def kb_crypto_amounts() -> InlineKeyboardMarkup:
    """Быстрый выбор суммы пополнения"""
    amounts = [10, 25, 50, 100, 250, 500]
    rows = []
    row = []
    for a in amounts:
        row.append(InlineKeyboardButton(text=f"{a}₽", callback_data=f"crypto_amt:{a}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="crypto_amt:custom")])
    rows.append([InlineKeyboardButton(text="← Назад",       callback_data="pay:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_card_amounts() -> InlineKeyboardMarkup:
    amounts = [10, 25, 50, 100, 250, 500]
    rows = []
    row = []
    for a in amounts:
        row.append(InlineKeyboardButton(text=f"{a}₽", callback_data=f"card_amt:{a}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="card_amt:custom")])
    rows.append([InlineKeyboardButton(text="← Назад",       callback_data="pay:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_payment_sent() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Главное меню", callback_data="pay:back")],
    ])


# ─────────────────────────────────────────────
#  КАСТОМНЫЕ ЭМОДЗИ (для пользователей)
# ─────────────────────────────────────────────
def kb_custom_emoji_list(emojis: list, page: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    rows = []
    for e in emojis:
        rows.append([InlineKeyboardButton(
            text=f"✦ {e['name']}",
            callback_data=f"use_emoji:{e['id']}"
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"emoji_page:{page-1}"))
    if (page + 1) * 10 < total:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶", callback_data=f"emoji_page:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="← Меню", callback_data="emoji:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────
#  АДМИН-ПАНЕЛЬ
# ─────────────────────────────────────────────
def kb_admin_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Пользователи",        callback_data="adm:users")],
        [InlineKeyboardButton(text="💰 Платежи (в ожидании)", callback_data="adm:payments")],
        [InlineKeyboardButton(text="✦ Кастомные эмодзи",    callback_data="adm:emoji")],
        [InlineKeyboardButton(text="📢 Рассылка",            callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="💲 Цена конвертации",    callback_data="adm:price")],
        [InlineKeyboardButton(text="🗄 База данных",         callback_data="adm:database")],
        [InlineKeyboardButton(text="← Закрыть",              callback_data="adm:close")],
    ])


def kb_admin_users(users: list, page: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    rows = []
    for u in users:
        name = u["username"] or u["full_name"] or str(u["telegram_id"])
        bal  = u["balance"]
        rows.append([InlineKeyboardButton(
            text=f"{'🔴' if u['is_banned'] else '🟢'} @{name}  |  {bal:.1f}₽",
            callback_data=f"adm_user:{u['telegram_id']}"
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀", callback_data=f"adm_upage:{page-1}"))
    if (page + 1) * 15 < total:
        nav_row.append(InlineKeyboardButton(text="▶", callback_data=f"adm_upage:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_user_actions(tg_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_label = "🔓 Разбанить" if is_banned else "🔨 Забанить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить баланс",  callback_data=f"adm_topup:{tg_id}")],
        [InlineKeyboardButton(text=ban_label,               callback_data=f"adm_ban:{tg_id}")],
        [InlineKeyboardButton(text="← Назад",               callback_data="adm:users")],
    ])


def kb_admin_payment(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_pay_ok:{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить",   callback_data=f"adm_pay_no:{payment_id}"),
        ],
        [InlineKeyboardButton(text="← Назад", callback_data="adm:payments")],
    ])


def kb_admin_emoji() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить эмодзи/стикер", callback_data="adm_emoji:add")],
        [InlineKeyboardButton(text="📋 Список",                  callback_data="adm_emoji:list")],
        [InlineKeyboardButton(text="← Назад",                    callback_data="adm:back")],
    ])


def kb_admin_emoji_item(emoji_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_emoji_del:{emoji_id}")],
        [InlineKeyboardButton(text="← Назад",   callback_data="adm_emoji:list")],
    ])


def kb_admin_db() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать БД",   callback_data="adm_db:download")],
        [InlineKeyboardButton(text="📤 Загрузить БД", callback_data="adm_db:upload")],
        [InlineKeyboardButton(text="← Назад",          callback_data="adm:back")],
    ])


def kb_back(callback: str = "adm:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data=callback)]
    ])
