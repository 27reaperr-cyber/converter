"""
handlers/admin.py — полная админ-панель

Разделы:
  • Статистика
  • Пользователи (список, просмотр, бан, пополнение)
  • Платежи (ожидающие подтверждения)
  • Кастомные эмодзи (добавить / удалить)
  • Рассылка
  • Цена конвертации
  • База данных (скачать / загрузить)
"""
import asyncio
import logging
import sys
import os
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, BufferedInputFile,
)
from aiogram.enums import ParseMode
from aiogram.filters import Command

from config import is_admin, ADMIN_IDS, DB_PATH, CONVERSION_PRICE
from database import (
    db_stats, db_all_users, db_get_user, db_ban_user,
    db_update_balance, db_get_payments_pending, db_get_payment,
    db_get_custom_emoji, db_count_custom_emoji,
    db_add_custom_emoji, db_delete_custom_emoji,
    db_set_global, db_get_global, get_db,
)
from states import AdminStates
from keyboards import (
    kb_admin_main, kb_admin_users, kb_admin_user_actions,
    kb_admin_payment, kb_admin_emoji, kb_admin_emoji_item,
    kb_admin_db, kb_back,
)

router = Router()
log = logging.getLogger(__name__)

PAGE_SIZE = 15


# ─────────────────────────────────────────────
#  ГЛАВНАЯ ПАНЕЛЬ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:back")
async def cb_adm_back(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    await call.message.edit_text(
        "🔧 <b>Панель администратора</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_main()
    )
    await call.answer()


@router.callback_query(F.data == "adm:close")
async def cb_adm_close(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    await call.message.delete()
    await call.answer()


# ─────────────────────────────────────────────
#  СТАТИСТИКА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:stats")
async def cb_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    s = db_stats()
    from database import get_db
    with get_db() as conn:
        top = conn.execute(
            "SELECT telegram_id, username, total_spent, conversions "
            "FROM users ORDER BY total_spent DESC LIMIT 5"
        ).fetchall()

    top_lines = ""
    for i, u in enumerate(top, 1):
        name = f"@{u['username']}" if u["username"] else str(u["telegram_id"])
        top_lines += f"  {i}. {name} — {u['total_spent']:.0f}₽ ({u['conversions']} конв.)\n"

    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n{'─'*22}\n"
        f"👥 Всего пользователей: <b>{s['users']}</b>\n"
        f"🎞 Конвертаций сегодня: <b>{s['active']}</b>\n"
        f"💰 Доход всего: <b>{s['revenue']:.2f}₽</b>\n"
        f"⏳ Платежей в ожидании: <b>{s['pending']}</b>\n\n"
        f"🏆 <b>Топ-5 пользователей:</b>\n{top_lines or '  —'}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:back")
    )
    await call.answer()


# ─────────────────────────────────────────────
#  ПОЛЬЗОВАТЕЛИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:users")
async def cb_users(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await _show_users_page(call, page=0)
    await call.answer()


@router.callback_query(F.data.startswith("adm_upage:"))
async def cb_users_page(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    page = int(call.data.split(":")[1])
    await _show_users_page(call, page)
    await call.answer()


async def _show_users_page(call: CallbackQuery, page: int):
    all_users = db_all_users()
    total = len(all_users)
    chunk = all_users[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    await call.message.edit_text(
        f"👥 <b>Пользователи</b>  ({total} чел.)",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_users(chunk, page, total)
    )


@router.callback_query(F.data.startswith("adm_user:"))
async def cb_user_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    tg_id = int(call.data.split(":")[1])
    u = db_get_user(tg_id)
    if not u:
        await call.answer("❌ Не найден", show_alert=True)
        return

    name = u["full_name"] or "—"
    uname = f"@{u['username']}" if u["username"] else "—"
    banned = "🔴 ДА" if u["is_banned"] else "🟢 НЕТ"

    await call.message.edit_text(
        f"👤 <b>Пользователь</b>\n{'─'*20}\n"
        f"ID: <code>{tg_id}</code>\n"
        f"Имя: <b>{name}</b>  {uname}\n"
        f"Баланс: <b>{u['balance']:.2f}₽</b>\n"
        f"Потрачено: <b>{u['total_spent']:.2f}₽</b>\n"
        f"Конвертаций: <b>{u['conversions']}</b>\n"
        f"Рег: <b>{u['reg_date']}</b>\n"
        f"Бан: <b>{banned}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_user_actions(tg_id, bool(u["is_banned"]))
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_ban:"))
async def cb_ban_user(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    tg_id = int(call.data.split(":")[1])
    u = db_get_user(tg_id)
    if not u: return

    new_ban = not bool(u["is_banned"])
    db_ban_user(tg_id, new_ban)
    action = "заблокирован" if new_ban else "разблокирован"

    await call.answer(f"✔ Пользователь {action}", show_alert=True)
    await cb_user_detail(call)  # обновить карточку

    if new_ban:
        try:
            await bot.send_message(tg_id, "🚫 Вы заблокированы администратором.")
        except Exception:
            pass


@router.callback_query(F.data.startswith("adm_topup:"))
async def cb_admin_topup(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    tg_id = int(call.data.split(":")[1])
    await state.set_state(AdminStates.topup_user_amount)
    await state.update_data(topup_user_id=tg_id)
    await call.message.edit_text(
        f"💰 Введите сумму для пополнения баланса пользователя <code>{tg_id}</code>:\n"
        f"(можно отрицательную — для списания)",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:users")
    )
    await call.answer()


@router.message(AdminStates.topup_user_amount)
async def adm_receive_topup(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id): return
    try:
        amount = float(msg.text.replace(",", ".").strip())
    except ValueError:
        await msg.answer("❌ Введите число")
        return

    data = await state.get_data()
    tg_id = data.get("topup_user_id")
    await state.clear()

    db_update_balance(tg_id, amount)
    from database import db_get_balance
    bal = db_get_balance(tg_id)

    await msg.answer(
        f"✔ {'Пополнено' if amount >= 0 else 'Списано'}: <b>{abs(amount):.2f}₽</b>\n"
        f"Новый баланс: <b>{bal:.2f}₽</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_main()
    )

    try:
        verb = "пополнен" if amount >= 0 else "списан"
        await bot.send_message(
            tg_id,
            f"💰 Ваш баланс {verb} администратором.\n"
            f"{'+ ' if amount >= 0 else ''}{amount:.2f}₽  →  Баланс: {bal:.2f}₽"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
#  ПЛАТЕЖИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:payments")
async def cb_payments(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    payments = db_get_payments_pending()
    if not payments:
        await call.message.edit_text(
            "✅ Нет ожидающих платежей.",
            reply_markup=kb_back("adm:back")
        )
        await call.answer()
        return

    lines = []
    for p in payments[:20]:
        name = p["username"] or p["full_name"] or str(p["telegram_id"])
        lines.append(
            f"◦ #{p['id']} | @{name} | {p['amount']}₽ | {p['method']} | {p['created_at']}"
        )

    await call.message.edit_text(
        f"⏳ <b>Ожидающие платежи</b> ({len(payments)}):\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:back")
    )
    await call.answer()


# ─────────────────────────────────────────────
#  КАСТОМНЫЕ ЭМОДЗИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:emoji")
async def cb_emoji_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    total = db_count_custom_emoji()
    await call.message.edit_text(
        f"✦ <b>Кастомные эмодзи</b>\nВсего: <b>{total}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_emoji()
    )
    await call.answer()


@router.callback_query(F.data == "adm_emoji:add")
async def cb_emoji_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.add_custom_emoji)
    await call.message.edit_text(
        "➕ <b>Добавить кастомный эмодзи</b>\n\n"
        "Отправьте стикер или изображение.\n"
        "Оно будет добавлено в библиотеку для пользователей.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:emoji")
    )
    await call.answer()


@router.message(AdminStates.add_custom_emoji, F.sticker | F.photo | F.document)
async def adm_receive_custom_emoji(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return

    file_id = None
    file_type = "image"
    if msg.sticker:
        file_id = msg.sticker.file_id
        file_type = "sticker"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "image"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "image"

    if not file_id:
        await msg.answer("❌ Не распознан файл")
        return

    # Сохраняем file_id во FSM, просим имя
    await state.set_state(AdminStates.add_emoji_name)
    await state.update_data(emoji_file_id=file_id, emoji_file_type=file_type)
    await msg.answer(
        "✏️ Введите название для этого эмодзи (например: <code>Fire</code>):",
        parse_mode=ParseMode.HTML,
    )


@router.message(AdminStates.add_emoji_name)
async def adm_receive_emoji_name(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    name = msg.text.strip()[:50]
    if not name:
        await msg.answer("❌ Введите название")
        return

    data = await state.get_data()
    file_id   = data.get("emoji_file_id")
    file_type = data.get("emoji_file_type", "sticker")
    await state.clear()

    try:
        db_add_custom_emoji(name, file_id, file_type, msg.from_user.id)
    except Exception as e:
        await msg.answer(f"❌ Ошибка (возможно, уже добавлен): {e}")
        return

    await msg.answer(
        f"✔ Эмодзи «<b>{name}</b>» добавлен!",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_emoji()
    )


@router.message(AdminStates.add_custom_emoji)
async def adm_emoji_wrong(msg: Message):
    await msg.answer("❌ Отправьте стикер или изображение")


@router.callback_query(F.data == "adm_emoji:list")
async def cb_emoji_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    emojis = db_get_custom_emoji(limit=20)
    if not emojis:
        await call.message.edit_text(
            "Список пуст.", reply_markup=kb_back("adm:emoji")
        )
        await call.answer()
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    for e in emojis:
        rows.append([InlineKeyboardButton(
            text=f"✦ {e['name']} ({e['file_type']})",
            callback_data=f"adm_emoji_view:{e['id']}"
        )])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:emoji")])
    await call.message.edit_text(
        f"✦ <b>Список эмодзи</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_emoji_view:"))
async def cb_emoji_view(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    emoji_id = int(call.data.split(":")[1])
    with get_db() as conn:
        row = conn.execute("SELECT * FROM custom_emoji WHERE id=?", (emoji_id,)).fetchone()
    if not row:
        await call.answer("❌ Не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"✦ <b>{row['name']}</b>\n"
        f"Тип: {row['file_type']}\n"
        f"File ID: <code>{row['file_id'][:32]}…</code>\n"
        f"Добавлен: {row['created_at']}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_emoji_item(emoji_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_emoji_del:"))
async def cb_emoji_del(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    emoji_id = int(call.data.split(":")[1])
    db_delete_custom_emoji(emoji_id)
    await call.message.edit_text(
        "🗑 Эмодзи удалён.",
        reply_markup=kb_back("adm:emoji")
    )
    await call.answer("✔ Удалено")


# ─────────────────────────────────────────────
#  ЦЕНА КОНВЕРТАЦИИ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:price")
async def cb_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.set_conversion_price)
    price = float(db_get_global("conversion_price", str(CONVERSION_PRICE)))
    await call.message.edit_text(
        f"💲 <b>Цена конвертации</b>\n\n"
        f"Текущая: <b>{price}₽</b>\n\n"
        f"Введите новую цену (₽):",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:back")
    )
    await call.answer()


@router.message(AdminStates.set_conversion_price)
async def adm_set_price(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try:
        price = float(msg.text.replace(",", ".").strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Введите положительное число")
        return

    await state.clear()
    db_set_global("conversion_price", str(price))
    await msg.answer(
        f"✔ Цена установлена: <b>{price}₽</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_main()
    )


# ─────────────────────────────────────────────
#  РАССЫЛКА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.broadcast_text)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте текст или фото с подписью.\n"
        "Будет разослано всем пользователям.\n\n"
        "Инлайн-кнопки: [[Текст|https://url]]",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:back")
    )
    await call.answer()


def _parse_inline_buttons(text: str):
    """Парсит [[Кнопка|url]] из текста, возвращает (clean_text, rows)"""
    import re
    buttons = re.findall(r'\[\[([^\]]+)\|([^\]]+)\]\]', text)
    clean = re.sub(r'\[\[[^\]]*\]\]', '', text).strip()
    rows = []
    row = []
    for i, (label, url) in enumerate(buttons):
        from aiogram.types import InlineKeyboardButton
        row.append(InlineKeyboardButton(text=label.strip(), url=url.strip()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return clean, rows


@router.message(AdminStates.broadcast_text)
async def adm_broadcast_send(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id): return
    await state.clear()

    all_users = db_all_users()
    text = msg.html_text or (msg.caption or "")
    clean_text, btn_rows = _parse_inline_buttons(text)

    from aiogram.types import InlineKeyboardMarkup
    markup = InlineKeyboardMarkup(inline_keyboard=btn_rows) if btn_rows else None

    sent = failed = 0

    for u in all_users:
        tg_id = u["telegram_id"]
        if u["is_banned"]:
            continue
        try:
            if msg.photo:
                await bot.send_photo(tg_id, msg.photo[-1].file_id,
                                     caption=clean_text or None,
                                     parse_mode=ParseMode.HTML if clean_text else None,
                                     reply_markup=markup)
            elif msg.document:
                await bot.send_document(tg_id, msg.document.file_id,
                                        caption=clean_text or None,
                                        parse_mode=ParseMode.HTML if clean_text else None,
                                        reply_markup=markup)
            elif msg.animation:
                await bot.send_animation(tg_id, msg.animation.file_id,
                                         caption=clean_text or None,
                                         parse_mode=ParseMode.HTML if clean_text else None,
                                         reply_markup=markup)
            else:
                await bot.send_message(tg_id, clean_text,
                                       parse_mode=ParseMode.HTML,
                                       reply_markup=markup)
            sent += 1
        except Exception:
            failed += 1

        if (sent + failed) % 30 == 0:
            await asyncio.sleep(1)  # anti-flood

    await msg.answer(
        f"✔ <b>Рассылка завершена</b>\n\n"
        f"◦ Доставлено: <b>{sent}</b>\n"
        f"◦ Ошибок: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_main()
    )


# ─────────────────────────────────────────────
#  БАЗА ДАННЫХ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "adm:database")
async def cb_database(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    await call.message.edit_text(
        f"🗄 <b>База данных</b>\n\n"
        f"◦ Файл: <code>{DB_PATH}</code>\n"
        f"◦ Размер: <b>{size / 1024:.1f} КБ</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admin_db()
    )
    await call.answer()


@router.callback_query(F.data == "adm_db:download")
async def cb_db_download(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    if not os.path.exists(DB_PATH):
        await call.answer("❌ Файл не найден", show_alert=True)
        return

    await call.answer("⏳ Отправляем…")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    await bot.send_document(
        call.from_user.id,
        FSInputFile(DB_PATH, filename=f"bot_backup_{ts}.db"),
        caption=f"🗄 <b>Бэкап БД</b> — {ts}",
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "adm_db:upload")
async def cb_db_upload(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(AdminStates.upload_db)
    await call.message.edit_text(
        "📤 <b>Загрузка БД</b>\n\n"
        "Отправь .db файл (бэкап).\n"
        "⚠️ Текущая БД будет заменена, бот перезапустится!",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("adm:database")
    )
    await call.answer()


@router.message(AdminStates.upload_db, F.document)
async def adm_receive_db(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id): return
    doc = msg.document
    if not (doc.file_name or "").endswith(".db"):
        await msg.answer("❌ Нужен файл с расширением .db")
        return

    await state.clear()
    tmp = DB_PATH + ".incoming"
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, destination=tmp)

    # Проверяем целостность SQLite
    try:
        import sqlite3
        test = sqlite3.connect(tmp)
        test.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        test.close()
    except Exception as e:
        os.remove(tmp)
        await msg.answer(f"❌ Файл повреждён: {e}")
        return

    # Бэкап текущей
    import shutil
    if os.path.exists(DB_PATH):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(DB_PATH, DB_PATH + f".bak_{ts}")

    shutil.move(tmp, DB_PATH)
    await msg.answer(
        "✔ <b>БД заменена, бот перезапускается…</b>",
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(1.5)
    os.execv(sys.executable, [sys.executable] + sys.argv)


@router.message(AdminStates.upload_db)
async def adm_db_wrong(msg: Message):
    await msg.answer("❌ Отправьте файл .db")
