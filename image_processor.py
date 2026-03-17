"""
image_processor.py — обработка изображений

Реализует:
  • Умную перекраску через HSV (заменяем Hue, сохраняем Value/Saturation)
  • Запасной метод: tint (grayscale × target_color) — multiply blending
  • Генерацию кадров (фон + эмодзи + notes + watermark)
  • Загрузку эмодзи из Twemoji CDN
  • Вотермарку с тенью и авторазмером
  • Рендер стикеров (.webp / .tgs)
"""

import io
import os
import math
import colorsys
import logging
import asyncio
import tempfile
from typing import Optional, Tuple

import numpy as np
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import FONTS_DIR, TEMP_DIR

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ
# ─────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Конвертирует #RRGGBB → (R, G, B)"""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def is_valid_hex(color: str) -> bool:
    import re
    return bool(re.fullmatch(r'#[0-9a-fA-F]{6}', color))


# ─────────────────────────────────────────────
#  УМНАЯ ПЕРЕКРАСКА — МЕТОД HSV (основной)
# ─────────────────────────────────────────────

def recolor_hsv(img: Image.Image, target_hex: str) -> Image.Image:
    """
    Метод 2 (лучший): HSV перекраска.

    Алгоритм:
      1. Конвертируем RGBA → RGB float32
      2. Переводим в HSV
      3. Заменяем Hue на Hue целевого цвета
      4. Для «серых» пикселей (S≈0) добавляем насыщенность пропорционально яркости
      5. Конвертируем обратно в RGB
      6. Возвращаем RGBA с оригинальным alpha-каналом

    Результат: сохраняются тени, блики, объём.
    """
    img_rgba = img.convert("RGBA")
    arr = np.array(img_rgba, dtype=np.float32) / 255.0

    r_t, g_t, b_t = [x / 255.0 for x in hex_to_rgb(target_hex)]
    target_h, target_s, target_v = colorsys.rgb_to_hsv(r_t, g_t, b_t)

    rgb   = arr[:, :, :3]          # (H, W, 3)
    alpha = arr[:, :, 3:4]         # (H, W, 1)

    # Векторизованное HSV через matplotlib
    try:
        from matplotlib.colors import rgb_to_hsv, hsv_to_rgb

        hsv = rgb_to_hsv(rgb)                    # (H, W, 3) → H, S, V

        original_s = hsv[:, :, 1:2]             # оригинальная насыщенность
        original_v = hsv[:, :, 2:3]             # оригинальная яркость

        # Заменяем Hue
        hsv[:, :, 0] = target_h

        # Для «серых» пикселей (S < 5%) добавляем насыщенность
        # Эффект «тонирования»: тени остаются тёмными, светлые области — светлее
        new_s = np.where(original_s > 0.05,
                         original_s,
                         target_s * original_v)
        hsv[:, :, 1] = new_s[:, :, 0]

        new_rgb = hsv_to_rgb(hsv)
        new_rgb = np.clip(new_rgb, 0.0, 1.0)

    except ImportError:
        # Фоллбэк: tint-метод (Метод 1)
        new_rgb = _tint_fallback(rgb, r_t, g_t, b_t)

    result = np.concatenate([new_rgb, alpha], axis=2)
    return Image.fromarray((result * 255).astype(np.uint8), "RGBA")


# ─────────────────────────────────────────────
#  МЕТОД TINT / SHADING (запасной, Метод 1)
# ─────────────────────────────────────────────

def recolor_tint(img: Image.Image, target_hex: str) -> Image.Image:
    """
    Метод 1: Tint/Shading.

    Алгоритм:
      new_color = brightness(pixel) * target_color

    Сохраняет тени и блики через яркость.
    + Multiply blending для глубины.
    """
    img_rgba = img.convert("RGBA")
    arr = np.array(img_rgba, dtype=np.float32) / 255.0

    r_t, g_t, b_t = [x / 255.0 for x in hex_to_rgb(target_hex)]
    rgb   = arr[:, :, :3]
    alpha = arr[:, :, 3:4]

    new_rgb = _tint_fallback(rgb, r_t, g_t, b_t)

    result = np.concatenate([new_rgb, alpha], axis=2)
    return Image.fromarray((result * 255).astype(np.uint8), "RGBA")


def _tint_fallback(rgb: np.ndarray, r_t: float, g_t: float, b_t: float) -> np.ndarray:
    """Perceptual luminance × target_color + multiply blending"""
    # Перцептуальная яркость (ITU-R 601)
    lum = (0.299 * rgb[:, :, 0:1] +
           0.587 * rgb[:, :, 1:2] +
           0.114 * rgb[:, :, 2:3])

    target = np.array([r_t, g_t, b_t], dtype=np.float32)
    tinted = lum * target

    # Multiply blending: смешиваем с оригинальным (сохраняет фактуру)
    multiplied = rgb * target
    new_rgb = 0.7 * tinted + 0.3 * multiplied

    return np.clip(new_rgb, 0.0, 1.0)


# ─────────────────────────────────────────────
#  ЗАГРУЗКА ЭМОДЗИ (Twemoji CDN)
# ─────────────────────────────────────────────

async def fetch_twemoji(emoji_char: str) -> Optional[Image.Image]:
    """
    Загружает PNG эмодзи из Twemoji CDN (72×72).
    Поддерживает составные эмодзи (ZWJ-sequences).
    """
    BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"

    def to_codepoints(text: str, skip_vs: bool = False) -> str:
        skip = {0xFE0F} if skip_vs else set()
        return '-'.join(f'{ord(c):x}' for c in text if ord(c) not in skip)

    for variant in [to_codepoints(emoji_char), to_codepoints(emoji_char, skip_vs=True)]:
        url = f"{BASE}/{variant}.png"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            ) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        img = Image.open(io.BytesIO(data)).convert("RGBA")
                        # Апскейл до 256×256 для лучшего качества
                        img = img.resize((256, 256), Image.LANCZOS)
                        return img
        except Exception as e:
            log.debug(f"Twemoji fetch failed ({url}): {e}")
    return None


# ─────────────────────────────────────────────
#  РЕНДЕР СТИКЕРА (.webp / .tgs)
# ─────────────────────────────────────────────

async def render_sticker(file_bytes: bytes, file_ext: str) -> Optional[Image.Image]:
    """
    Рендерит стикер в PIL Image (RGBA).
    .webp — напрямую через Pillow
    .tgs  — Lottie через библиотеку lottie (если установлена), иначе thumbnail
    """
    if file_ext in ('.webp', '.png', '.jpg', '.jpeg'):
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
            # Anti-aliasing: масштабируем до 256×256
            img = img.resize((256, 256), Image.LANCZOS)
            return img
        except Exception as e:
            log.warning(f"Sticker open failed: {e}")
            return None

    if file_ext == '.tgs':
        return await _render_tgs(file_bytes)

    return None


async def _render_tgs(data: bytes) -> Optional[Image.Image]:
    """Рендер Lottie (.tgs) в первый кадр PNG"""
    try:
        import gzip
        import json

        raw = gzip.decompress(data)
        lottie_json = json.loads(raw)

        try:
            import lottie
            from lottie.exporters.cairo import export_png
            from lottie import parsers

            anim = parsers.tgs.parse_tgs(io.BytesIO(data))
            buf = io.BytesIO()
            export_png(anim, buf, frame=0)
            buf.seek(0)
            img = Image.open(buf).convert("RGBA")
            return img.resize((256, 256), Image.LANCZOS)
        except ImportError:
            pass

        # Фоллбэк: генерируем placeholder с первой буквой
        img = Image.new("RGBA", (256, 256), (80, 80, 200, 255))
        draw = ImageDraw.Draw(img)
        draw.text((100, 80), "TGS", fill=(255, 255, 255, 255))
        return img

    except Exception as e:
        log.warning(f"TGS render failed: {e}")
        return None


# ─────────────────────────────────────────────
#  ШРИФТЫ
# ─────────────────────────────────────────────

def get_font(font_name: str = "default", size: int = 36) -> ImageFont.FreeTypeFont:
    """Загружает шрифт: сначала из папки fonts/, потом системные, потом дефолтный"""
    if font_name not in ("default", ""):
        path = os.path.join(FONTS_DIR, font_name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    system_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    for fp in system_fonts:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue

    # Финальный фоллбэк — встроенный PIL шрифт
    return ImageFont.load_default()


def list_fonts() -> list:
    """Список доступных TTF шрифтов"""
    fonts = ["default"]
    if os.path.exists(FONTS_DIR):
        for f in sorted(os.listdir(FONTS_DIR)):
            if f.lower().endswith(('.ttf', '.otf')):
                fonts.append(f)
    return fonts


# ─────────────────────────────────────────────
#  ВОТЕРМАРКА
# ─────────────────────────────────────────────

def add_watermark(
    img: Image.Image,
    text: str,
    font_name: str = "default",
    color: str = "#ffffff",
    position: str = "bottom_right",
    opacity: float = 0.7,
    font_size: int = None,
) -> Image.Image:
    """
    Накладывает вотермарку:
    • Авторазмер шрифта (~3% от минимального измерения)
    • Тень текста (2-слойная)
    • Настраиваемая позиция
    • Прозрачность через alpha
    """
    if not text:
        return img

    img = img.copy().convert("RGBA")
    w, h = img.size

    if font_size is None:
        font_size = max(14, int(min(w, h) * 0.035))

    font = get_font(font_name, font_size)

    # Создаём прозрачный слой
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad = max(12, int(min(w, h) * 0.02))
    positions = {
        "top_left":     (pad, pad),
        "top_right":    (w - tw - pad, pad),
        "center":       ((w - tw) // 2, (h - th) // 2),
        "bottom_left":  (pad, h - th - pad),
        "bottom_right": (w - tw - pad, h - th - pad),
    }
    x, y = positions.get(position, positions["bottom_right"])

    r, g, b = hex_to_rgb(color)
    alpha_val = int(opacity * 255)

    # Тень (2 уровня для мягкости)
    for shift, shadow_alpha in [((2, 2), int(alpha_val * 0.6)), ((1, 1), int(alpha_val * 0.4))]:
        draw.text(
            (x + shift[0], y + shift[1]),
            text, font=font,
            fill=(0, 0, 0, shadow_alpha)
        )

    # Основной текст
    draw.text((x, y), text, font=font, fill=(r, g, b, alpha_val))

    return Image.alpha_composite(img, overlay)


# ─────────────────────────────────────────────
#  NOTES (текст под эмодзи)
# ─────────────────────────────────────────────

def add_notes(img: Image.Image, text: str, font_name: str = "default") -> Image.Image:
    """Добавляет заметки по центру снизу изображения"""
    if not text:
        return img

    img = img.copy().convert("RGBA")
    w, h = img.size

    size = max(14, int(min(w, h) * 0.03))
    font = get_font(font_name, size)
    draw = ImageDraw.Draw(img)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x = (w - tw) // 2
    y = h - th - int(h * 0.06)

    # Тень
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 180))
    # Текст
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 220))

    return img


# ─────────────────────────────────────────────
#  ГЕНЕРАЦИЯ ОДНОГО КАДРА
# ─────────────────────────────────────────────

def create_frame(
    emoji_img: Image.Image,
    bg_color: str = "#1a1a2e",
    resolution: str = "1920x530",
    custom_bg: Optional[Image.Image] = None,
    notes: str = "",
    watermark_settings: Optional[dict] = None,
    rotation: float = 0.0,
    scale: float = 1.0,
    offset_y: int = 0,
) -> Image.Image:
    """
    Генерирует один кадр:
      1. Создаёт фон (цвет или пользовательское изображение)
      2. Масштабирует и накладывает эмодзи (с rotation, scale, offset)
      3. Добавляет notes
      4. Добавляет вотермарку
    """
    # Парсим разрешение
    try:
        width, height = map(int, resolution.split('x'))
    except Exception:
        width, height = 1920, 530

    # Создаём фон
    if custom_bg is not None:
        bg = custom_bg.copy().resize((width, height), Image.LANCZOS).convert("RGBA")
    else:
        try:
            r, g, b = hex_to_rgb(bg_color)
        except Exception:
            r, g, b = 26, 26, 46
        bg = Image.new("RGBA", (width, height), (r, g, b, 255))

    # Масштабируем эмодзи
    max_side = int(min(width, height) * 0.60 * scale)
    ew, eh = emoji_img.size
    ratio = min(max_side / max(ew, 1), max_side / max(eh, 1))
    new_ew = max(1, int(ew * ratio))
    new_eh = max(1, int(eh * ratio))
    emoji_scaled = emoji_img.resize((new_ew, new_eh), Image.LANCZOS)

    # Поворот (с сохранением прозрачности)
    if abs(rotation) > 0.1:
        emoji_scaled = emoji_scaled.rotate(
            rotation, expand=True, resample=Image.BICUBIC
        )

    # Центрирование + вертикальный офсет
    ex = (width - emoji_scaled.width) // 2
    ey = (height - emoji_scaled.height) // 2 + offset_y

    # Накладываем эмодзи на фон (RGBA-compositing)
    bg.paste(emoji_scaled, (ex, ey), emoji_scaled)

    # Добавляем заметки
    if notes:
        bg = add_notes(bg, notes)

    # Добавляем вотермарку
    if watermark_settings and watermark_settings.get("text"):
        bg = add_watermark(
            bg,
            text=watermark_settings["text"],
            font_name=watermark_settings.get("font", "default"),
            color=watermark_settings.get("color", "#ffffff"),
            position=watermark_settings.get("position", "bottom_right"),
            opacity=float(watermark_settings.get("opacity", 0.7)),
        )

    return bg


# ─────────────────────────────────────────────
#  ПОЛНЫЙ ПАЙПЛАЙН: ВХОД → ГОТОВЫЙ КАДР
# ─────────────────────────────────────────────

async def process_input_to_image(
    input_data: bytes,
    input_type: str,       # 'emoji', 'sticker_webp', 'sticker_tgs', 'image'
    input_text: str = "",  # если type=='emoji'
    settings: dict = None,
) -> Optional[Image.Image]:
    """
    Превращает пользовательский ввод в PIL Image (RGBA) для дальнейшей генерации.
    Применяет перекраску если emoji_color задан.
    """
    if settings is None:
        settings = {}

    emoji_img: Optional[Image.Image] = None

    # ── Получаем изображение ──────────────────
    if input_type == 'emoji' and input_text:
        emoji_img = await fetch_twemoji(input_text)
        if emoji_img is None:
            # Fallback: рисуем текст напрямую
            emoji_img = _render_emoji_text(input_text)

    elif input_type in ('sticker_webp', 'sticker_tgs', 'image'):
        ext = {
            'sticker_webp': '.webp',
            'sticker_tgs':  '.tgs',
            'image':        '.png',
        }.get(input_type, '.png')
        emoji_img = await render_sticker(input_data, ext)

    if emoji_img is None:
        return None

    # ── Применяем перекраску ──────────────────
    emoji_color = settings.get("emoji_color", "")
    if emoji_color and is_valid_hex(emoji_color):
        try:
            emoji_img = recolor_hsv(emoji_img, emoji_color)
        except Exception as e:
            log.warning(f"HSV recolor failed, using tint: {e}")
            try:
                emoji_img = recolor_tint(emoji_img, emoji_color)
            except Exception as e2:
                log.warning(f"Tint recolor also failed: {e2}")

    return emoji_img


def _render_emoji_text(text: str, size: int = 256) -> Image.Image:
    """Рисует текст-эмодзи как изображение (фоллбэк)"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Пробуем emoji-шрифт
    emoji_fonts = [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
    ]
    font = None
    for fp in emoji_fonts:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, int(size * 0.7))
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2
    draw.text((x, y), text, font=font)
    return img
