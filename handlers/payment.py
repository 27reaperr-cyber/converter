"""
handlers/payment.py — пополнение баланса
  • CryptoBot (USDT/TON/BTC)
  • Банковская карта (ручное подтверждение администратором)
"""
import logging
import aiohttp
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode

from config import (
    CRYPTOBOT_TOKEN, CRYPTOBOT_API,
    BANK_CARD, BANK_NAME, BANK_RECEIVER,
    ADMIN_IDS,
)
from database import (
    db_get_balance, db_update_balance,
    db_create_payment, db_confirm_payment, db_get_payment,
)
from states import PaymentStates
from keyboards import (
    kb_topup, kb_crypto_amounts, kb_card_amounts,
    kb_payment_sent, kb_back, kb_main_reply
)

router = Router()
log = logging.getLogger(__name__)

MIN_TOPUP = 10.0
MAX_TOPUP = 50000.0


# ─────────────────────────────────────────────
#  ОТКРЫТЬ МЕНЮ ПОПОЛНЕНИЯ
# ─────────────────────────────────────────────
@router.message(F.text == "💳 Пополнить")
@router.message(Command("topup"))
async def cmd_topup(msg: Message, state: FSMContext):
    await state.clear()
    balance = db_get_balance(msg.from_user.id)
    await msg.answer(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{balance:.2f}₽</b>\n\n"
        f"Выберите способ оплаты:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_topup(),
    )


@router.callback_query(F.data == "pay:back")
async def cb_pay_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = db_get_balance(call.from_user.id)
    await call.message.edit_text(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{balance:.2f}₽</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_topup(),
    )
    await call.answer()


# ─────────────────────────────────────────────
#  CRYPTOBOT
# ─────────────────────────────────────────────
@router.callback_query(F.data == "pay:crypto")
async def cb_pay_crypto(call: CallbackQuery, state: FSMContext):
    if not CRYPTOBOT_TOKEN:
        await call.answer("⚠️ CryptoBot не настроен", show_alert=True)
        return
    await call.message.edit_text(
        "💎 <b>Пополнение через CryptoBot</b>\n\n"
        "Выберите сумму (₽):",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_crypto_amounts(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("crypto_amt:"))
async def cb_crypto_amount(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":")[1]
    if val == "custom":
        await state.set_state(PaymentStates.waiting_amount)
        await state.update_data(method="crypto")
        await call.message.edit_text(
            "✏️ Введите сумму пополнения (₽):",
            reply_markup=kb_back("pay:crypto")
        )
    else:
        amount = float(val)
        await _create_crypto_invoice(call, state, amount)
    await call.answer()


@router.message(PaymentStates.waiting_amount)
async def receive_custom_amount(msg: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(msg.text.replace(",", ".").strip())
    except ValueError:
        await msg.answer("❌ Введите число, например: <code>50</code>",
                         parse_mode=ParseMode.HTML)
        return

    if amount < MIN_TOPUP:
        await msg.answer(f"❌ Минимальная сумма: <b>{MIN_TOPUP:.0f}₽</b>",
                         parse_mode=ParseMode.HTML)
        return
    if amount > MAX_TOPUP:
        await msg.answer(f"❌ Максимальная сумма: <b>{MAX_TOPUP:.0f}₽</b>",
                         parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    method = data.get("method", "crypto")

    if method == "crypto":
        await _create_crypto_invoice_msg(msg, state, amount)
    else:
        await _show_card_details(msg, state, amount)


async def _create_crypto_invoice(call: CallbackQuery, state: FSMContext, amount: float):
    """Создаёт инвойс в CryptoBot и отправляет ссылку"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    try:
        # CryptoBot работает в USD, конвертируем ₽ → USD (примерный курс)
        # В реальности нужен актуальный курс; здесь используем USDT напрямую
        # Для рублей лучше принимать USDT по курсу
        # Упрощённо: 1 USD ≈ 90 RUB
        usd_amount = round(amount / 90, 2)
        if usd_amount < 0.01:
            usd_amount = 0.01

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOBOT_API}/createInvoice",
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN},
                json={
                    "asset": "USDT",
                    "amount": str(usd_amount),
                    "description": f"Пополнение баланса {amount:.0f}₽",
                    "expires_in": 3600,
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Unknown error"))

        invoice = data["result"]
        invoice_url = invoice["bot_invoice_url"]
        invoice_id  = str(invoice["invoice_id"])

        payment_id = db_create_payment(
            call.from_user.id, amount, "cryptobot", invoice_id
        )

        await call.message.edit_text(
            f"💎 <b>Оплата через CryptoBot</b>\n\n"
            f"Сумма: <b>{amount:.0f}₽</b> (~{usd_amount} USDT)\n\n"
            f"Нажмите кнопку ниже для оплаты.\n"
            f"После оплаты баланс пополнится автоматически.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice_url)],
                [InlineKeyboardButton(text="✅ Проверить оплату",
                                      callback_data=f"check_crypto:{payment_id}")],
                [InlineKeyboardButton(text="← Отмена", callback_data="pay:back")],
            ])
        )

    except Exception as e:
        log.exception("CryptoBot invoice creation failed")
        await call.message.edit_text(
            f"❌ Ошибка создания инвойса: {e}",
            reply_markup=kb_back("pay:back")
        )


async def _create_crypto_invoice_msg(msg: Message, state: FSMContext, amount: float):
    """Версия для Message (кастомная сумма)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await state.clear()

    try:
        usd_amount = round(amount / 90, 2)
        if usd_amount < 0.01:
            usd_amount = 0.01

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOBOT_API}/createInvoice",
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN},
                json={
                    "asset": "USDT",
                    "amount": str(usd_amount),
                    "description": f"Пополнение {amount:.0f}₽",
                    "expires_in": 3600,
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data_resp = await resp.json()

        if not data_resp.get("ok"):
            raise RuntimeError(data_resp.get("error", "Unknown"))

        invoice = data_resp["result"]
        invoice_url = invoice["bot_invoice_url"]
        invoice_id  = str(invoice["invoice_id"])

        payment_id = db_create_payment(msg.from_user.id, amount, "cryptobot", invoice_id)

        await msg.answer(
            f"💎 <b>Оплата через CryptoBot</b>\n\n"
            f"Сумма: <b>{amount:.0f}₽</b> (~{usd_amount} USDT)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice_url)],
                [InlineKeyboardButton(text="✅ Проверить оплату",
                                      callback_data=f"check_crypto:{payment_id}")],
                [InlineKeyboardButton(text="← Назад", callback_data="pay:back")],
            ])
        )
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data.startswith("check_crypto:"))
async def cb_check_crypto(call: CallbackQuery, bot: Bot):
    """Проверяет статус оплаты в CryptoBot"""
    payment_id = int(call.data.split(":")[1])
    payment = db_get_payment(payment_id)

    if not payment:
        await call.answer("❌ Платёж не найден", show_alert=True)
        return

    if payment["status"] == "paid":
        await call.answer("✅ Уже оплачено!", show_alert=True)
        return

    if not CRYPTOBOT_TOKEN:
        await call.answer("⚠️ CryptoBot не настроен", show_alert=True)
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CRYPTOBOT_API}/getInvoices",
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN},
                params={"invoice_ids": payment["invoice_id"]},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

        if not data.get("ok"):
            await call.answer("❌ Ошибка проверки", show_alert=True)
            return

        invoices = data["result"].get("items", [])
        if not invoices:
            await call.answer("⏳ Счёт не найден", show_alert=True)
            return

        inv = invoices[0]
        if inv["status"] == "paid":
            amount = float(payment["amount"])
            db_confirm_payment(payment_id)
            db_update_balance(call.from_user.id, amount)
            balance = db_get_balance(call.from_user.id)
            await call.message.edit_text(
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"Пополнено: <b>{amount:.2f}₽</b>\n"
                f"Новый баланс: <b>{balance:.2f}₽</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_payment_sent()
            )
            await call.answer("✅ Оплачено!")
        else:
            await call.answer("⏳ Оплата ещё не поступила", show_alert=True)

    except Exception as e:
        log.exception("CryptoBot check failed")
        await call.answer(f"❌ Ошибка: {e}", show_alert=True)


# ─────────────────────────────────────────────
#  БАНКОВСКАЯ КАРТА
# ─────────────────────────────────────────────
@router.callback_query(F.data == "pay:card")
async def cb_pay_card(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "🏦 <b>Оплата картой</b>\n\n"
        "Выберите сумму пополнения (₽):",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_card_amounts(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("card_amt:"))
async def cb_card_amount(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":")[1]
    if val == "custom":
        await state.set_state(PaymentStates.waiting_amount)
        await state.update_data(method="card")
        await call.message.edit_text(
            "✏️ Введите сумму пополнения (₽):",
            reply_markup=kb_back("pay:card")
        )
    else:
        amount = float(val)
        await _show_card_details_cb(call, state, amount)
    await call.answer()


async def _show_card_details_cb(call: CallbackQuery, state: FSMContext, amount: float):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    payment_id = db_create_payment(call.from_user.id, amount, "card")

    await call.message.edit_text(
        f"🏦 <b>Оплата картой</b>\n\n"
        f"Сумма перевода: <b>{amount:.0f}₽</b>\n\n"
        f"💳 Реквизиты:\n"
        f"Банк: <b>{BANK_NAME}</b>\n"
        f"Карта: <code>{BANK_CARD}</code>\n"
        f"Получатель: <b>{BANK_RECEIVER}</b>\n\n"
        f"⚠️ В комментарии укажите: <code>ID{call.from_user.id}</code>\n\n"
        f"После перевода нажмите «Отправил чек» и прикрепите скриншот.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📎 Отправил чек",
                                  callback_data=f"card_receipt:{payment_id}")],
            [InlineKeyboardButton(text="← Отмена", callback_data="pay:back")],
        ])
    )


async def _show_card_details(msg: Message, state: FSMContext, amount: float):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await state.clear()
    payment_id = db_create_payment(msg.from_user.id, amount, "card")

    await msg.answer(
        f"🏦 <b>Оплата картой</b>\n\n"
        f"Сумма: <b>{amount:.0f}₽</b>\n\n"
        f"💳 Реквизиты:\n"
        f"Банк: <b>{BANK_NAME}</b>\n"
        f"Карта: <code>{BANK_CARD}</code>\n"
        f"Получатель: <b>{BANK_RECEIVER}</b>\n\n"
        f"⚠️ Комментарий: <code>ID{msg.from_user.id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📎 Отправил чек",
                                  callback_data=f"card_receipt:{payment_id}")],
            [InlineKeyboardButton(text="← Отмена", callback_data="pay:back")],
        ])
    )


@router.callback_query(F.data.startswith("card_receipt:"))
async def cb_card_receipt(call: CallbackQuery, state: FSMContext):
    payment_id = int(call.data.split(":")[1])
    await state.set_state(PaymentStates.waiting_card_receipt)
    await state.update_data(payment_id=payment_id)
    await call.message.edit_text(
        "📎 <b>Отправьте скриншот чека</b>\n\n"
        "Прикрепите фото квитанции о переводе.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back("pay:back")
    )
    await call.answer()


@router.message(PaymentStates.waiting_card_receipt, F.photo)
async def receive_receipt(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    payment_id = data.get("payment_id")
    await state.clear()

    if not payment_id:
        await msg.answer("❌ Ошибка: не найден ID платежа")
        return

    receipt_file_id = msg.photo[-1].file_id
    db_confirm_payment(payment_id, receipt_file_id)  # статус остаётся pending — ждёт адм.

    payment = db_get_payment(payment_id)
    amount = payment["amount"] if payment else "?"

    # Уведомляем администраторов
    from keyboards import kb_admin_payment
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                receipt_file_id,
                caption=(
                    f"💰 <b>Новый платёж (карта)</b>\n\n"
                    f"User: <code>{msg.from_user.id}</code> "
                    f"(@{msg.from_user.username or '—'})\n"
                    f"Сумма: <b>{amount}₽</b>\n"
                    f"ID платежа: <b>{payment_id}</b>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb_admin_payment(payment_id)
            )
        except Exception as e:
            log.warning(f"Admin notify failed: {e}")

    await msg.answer(
        "✅ <b>Чек отправлен!</b>\n\n"
        "Администратор проверит и пополнит баланс в течение нескольких минут.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main_reply()
    )


@router.message(PaymentStates.waiting_card_receipt)
async def receipt_wrong(msg: Message):
    await msg.answer("❌ Отправьте фото чека (скриншот квитанции)")


# ─────────────────────────────────────────────
#  ОБРАБОТКА ПОДТВЕРЖДЕНИЯ АДМИНИСТРАТОРОМ
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("adm_pay_ok:"))
async def adm_confirm_payment(call: CallbackQuery, bot: Bot):
    from config import is_admin
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Нет доступа", show_alert=True)
        return

    payment_id = int(call.data.split(":")[1])
    payment = db_get_payment(payment_id)
    if not payment:
        await call.answer("❌ Платёж не найден", show_alert=True)
        return

    if payment["status"] == "paid":
        await call.answer("✅ Уже подтверждён", show_alert=True)
        return

    amount = float(payment["amount"])
    user_tg = payment["telegram_id"]

    db_confirm_payment(payment_id)
    db_update_balance(user_tg, amount)

    await call.message.edit_caption(
        call.message.caption + f"\n\n✅ <b>ПОДТВЕРЖДЕНО</b> (+{amount}₽)",
        parse_mode=ParseMode.HTML,
    )
    await call.answer("✅ Платёж подтверждён")

    # Уведомляем пользователя
    balance = db_get_balance(user_tg)
    try:
        await bot.send_message(
            user_tg,
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"Зачислено: <b>{amount:.2f}₽</b>\n"
            f"Текущий баланс: <b>{balance:.2f}₽</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_pay_no:"))
async def adm_reject_payment(call: CallbackQuery, bot: Bot):
    from config import is_admin
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Нет доступа", show_alert=True)
        return

    payment_id = int(call.data.split(":")[1])
    payment = db_get_payment(payment_id)
    if not payment:
        await call.answer("❌ Не найден", show_alert=True)
        return

    from database import get_db
    with get_db() as conn:
        conn.execute(
            "UPDATE payments SET status='rejected' WHERE id=?", (payment_id,)
        )
        conn.commit()

    await call.message.edit_caption(
        (call.message.caption or "") + "\n\n❌ <b>ОТКЛОНЕНО</b>",
        parse_mode=ParseMode.HTML,
    )
    await call.answer("❌ Отклонено")

    try:
        await bot.send_message(
            payment["telegram_id"],
            "❌ <b>Платёж отклонён.</b>\n\nОбратитесь в поддержку.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
