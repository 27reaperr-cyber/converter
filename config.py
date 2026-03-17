"""
config.py — централизованная конфигурация бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
ADMIN_IDS   = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]
BOT_USERNAME = os.getenv("BOT_USERNAME", "mybot")

# ── Оплата: CryptoBot ────────────────────────
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "")
CRYPTOBOT_API   = "https://pay.crypt.bot/api"

# ── Оплата: банковская карта ──────────────────
BANK_CARD     = os.getenv("BANK_CARD", "4400000000000000")
BANK_NAME     = os.getenv("BANK_NAME", "Т-Банк")
BANK_RECEIVER = os.getenv("BANK_RECEIVER", "Иванов И.И.")

# ── Тарифы ────────────────────────────────────
CONVERSION_PRICE  = float(os.getenv("CONVERSION_PRICE", "5.0"))   # рублей за 1 конвертацию
PREVIEW_FREE      = True    # предпросмотр бесплатен

# ── Пути ──────────────────────────────────────
DB_PATH    = os.getenv("DB_PATH", "database.db")
TEMP_DIR   = os.getenv("TEMP_DIR", "temp")
FONTS_DIR  = os.getenv("FONTS_DIR", "fonts")

# ── Лимиты ────────────────────────────────────
MAX_FRAMES      = 60     # кадров в GIF (1 секунда @ 60fps)
GIF_DURATION_MS = 17     # ~60fps
MAX_RESOLUTION  = (3840, 2160)
TEMP_TTL_HOURS  = 2      # хранить temp-файлы N часов

# ── Доступные разрешения ──────────────────────
RESOLUTIONS = [
    ("1920×530  (Баннер)",    "1920x530"),
    ("1280×720  (HD)",        "1280x720"),
    ("1920×1080 (Full HD)",   "1920x1080"),
    ("512×512   (Квадрат)",   "512x512"),
    ("800×600   (Стандарт)",  "800x600"),
    ("640×360   (Мини)",      "640x360"),
]

# ── Форматы вывода ────────────────────────────
FORMATS = ["GIF", "PNG", "MP4"]

# ── Позиции вотермарки ────────────────────────
WM_POSITIONS = {
    "top_left":     "↖ Верх-лево",
    "top_right":    "↗ Верх-право",
    "center":       "✦ По центру",
    "bottom_left":  "↙ Низ-лево",
    "bottom_right": "↘ Низ-право",
}

# ── Реферальная программа ─────────────────────
REFERRAL_PCT    = float(os.getenv("REFERRAL_PCT", "5"))
TRANSFER_FEE_PCT = float(os.getenv("TRANSFER_FEE_PCT", "2.5"))
TRANSFER_FEE_MIN = float(os.getenv("TRANSFER_FEE_MIN", "1"))

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
