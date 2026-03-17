"""
states.py — FSM-состояния для всех диалоговых потоков
"""
from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    """Настройки пользователя"""
    waiting_bg_color    = State()   # ждём HEX цвет фона
    waiting_emoji_color = State()   # ждём HEX цвет эмодзи
    waiting_resolution  = State()   # (используем inline-кнопки)
    waiting_format      = State()   # (используем inline-кнопки)
    waiting_custom_media = State()  # ждём фото/стикер как фон
    waiting_notes       = State()   # ждём текст заметок


class WatermarkStates(StatesGroup):
    """Настройки вотермарки"""
    waiting_text     = State()   # ждём текст вотермарки
    waiting_color    = State()   # ждём HEX цвет
    waiting_font     = State()   # (inline-кнопки)
    waiting_position = State()   # (inline-кнопки)


class MediaStates(StatesGroup):
    """Обработка входящей медиа"""
    waiting_emoji_input  = State()   # ждём emoji-текст / стикер / фото
    processing           = State()   # идёт обработка


class PaymentStates(StatesGroup):
    """Платёжные потоки"""
    waiting_amount       = State()   # ждём сумму пополнения
    waiting_card_receipt = State()   # ждём фото чека (банк)
    waiting_crypto_check = State()   # ожидание подтверждения CryptoBot


class AdminStates(StatesGroup):
    """Администрирование"""
    broadcast_text    = State()   # рассылка
    add_custom_emoji  = State()   # добавление кастомного эмодзи
    add_emoji_name    = State()   # имя для кастомного эмодзи
    upload_db         = State()   # загрузка БД
    set_conversion_price = State()  # изменение цены конвертации
    ban_user_id       = State()   # бан пользователя по ID
    topup_user        = State()   # пополнение баланса пользователя
    topup_user_amount = State()   # сумма пополнения
    confirm_payment   = State()   # подтверждение оплаты картой
