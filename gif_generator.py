"""
gif_generator.py — генерация GIF (60fps), PNG, MP4

Анимация GIF:
  • scale-pulse: 1.0 → 1.05 → 1.0  (синус, 1 цикл)
  • rotation:    +5° → -5° → +5°    (синус, 1 цикл)
  • float:       0 → -8px → 0       (синус, 1 цикл)
  60 кадров = 1 секунда цикла
"""

import io
import math
import logging
from typing import List, Optional, Tuple
from PIL import Image

from config import MAX_FRAMES, GIF_DURATION_MS
from image_processor import create_frame

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ПАРАМЕТРЫ АНИМАЦИИ
# ─────────────────────────────────────────────

def _animation_params(frame_idx: int, total: int) -> Tuple[float, float, int]:
    """
    Возвращает (scale, rotation, offset_y) для кадра frame_idx.
    Использует синусоиды для плавной зацикленной анимации.
    """
    t = frame_idx / total  # 0.0 → 1.0

    scale    = 1.0 + 0.04 * math.sin(t * 2 * math.pi)       # пульсация ±4%
    rotation = 4.0 * math.sin(t * 2 * math.pi)               # вращение ±4°
    offset_y = int(-7 * math.sin(t * 2 * math.pi))           # плавание ±7px

    return scale, rotation, offset_y


# ─────────────────────────────────────────────
#  ГЕНЕРАЦИЯ КАДРОВ
# ─────────────────────────────────────────────

def _build_wm_settings(settings: dict) -> dict:
    return {
        "text":     settings.get("wm_text", ""),
        "font":     settings.get("wm_font", "default"),
        "color":    settings.get("wm_color", "#ffffff"),
        "position": settings.get("wm_position", "bottom_right"),
        "opacity":  float(settings.get("wm_opacity", 0.7)),
    }


def generate_frames(
    emoji_img: Image.Image,
    settings: dict,
    custom_bg: Optional[Image.Image] = None,
    n_frames: int = MAX_FRAMES,
    animated: bool = True,
) -> List[Image.Image]:
    """
    Генерирует список кадров PIL Image (RGB).
    animated=False → единственный статичный кадр (для PNG / предпросмотра).
    """
    wm = _build_wm_settings(settings)
    bg_color  = settings.get("bg_color",   "#1a1a2e")
    resolution = settings.get("resolution", "1920x530")
    notes     = settings.get("notes",      "")

    if not animated:
        frame = create_frame(
            emoji_img=emoji_img,
            bg_color=bg_color,
            resolution=resolution,
            custom_bg=custom_bg,
            notes=notes,
            watermark_settings=wm,
        )
        return [frame.convert("RGB")]

    frames: List[Image.Image] = []
    for i in range(n_frames):
        scale, rotation, offset_y = _animation_params(i, n_frames)
        frame = create_frame(
            emoji_img=emoji_img,
            bg_color=bg_color,
            resolution=resolution,
            custom_bg=custom_bg,
            notes=notes,
            watermark_settings=wm,
            rotation=rotation,
            scale=scale,
            offset_y=offset_y,
        )
        frames.append(frame.convert("RGB"))

    return frames


# ─────────────────────────────────────────────
#  СОХРАНЕНИЕ GIF
# ─────────────────────────────────────────────

def save_gif_bytes(frames: List[Image.Image], duration_ms: int = GIF_DURATION_MS) -> bytes:
    """
    Сохраняет GIF в bytes.
    duration_ms = 17 ≈ 60fps (GIF-игроки в реальности покажут ~25-50fps,
    т.к. минимально корректно обрабатываемое значение у большинства = 20ms).
    loop=0 → бесконечный цикл.
    """
    buf = io.BytesIO()

    # PIL GIF палитризует RGB → потеря некоторых цветов, но оптимальный размер
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
        disposal=2,   # replace frame (чище анимация)
    )
    buf.seek(0)
    return buf.getvalue()


def save_gif_to_file(frames: List[Image.Image], path: str, duration_ms: int = GIF_DURATION_MS) -> str:
    data = save_gif_bytes(frames, duration_ms)
    with open(path, "wb") as f:
        f.write(data)
    return path


# ─────────────────────────────────────────────
#  СОХРАНЕНИЕ PNG
# ─────────────────────────────────────────────

def save_png_bytes(frame: Image.Image) -> bytes:
    """Сохраняет PNG в bytes (RGBA для прозрачности)"""
    buf = io.BytesIO()
    frame_rgba = frame.convert("RGBA")
    frame_rgba.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()


def save_png_to_file(frame: Image.Image, path: str) -> str:
    with open(path, "wb") as f:
        f.write(save_png_bytes(frame))
    return path


# ─────────────────────────────────────────────
#  СОХРАНЕНИЕ MP4 (опционально, требует ffmpeg)
# ─────────────────────────────────────────────

def save_mp4_bytes(frames: List[Image.Image], fps: int = 30) -> bytes:
    """
    Сохраняет MP4 через imageio (требует ffmpeg в системе).
    При недоступности — выбрасывает RuntimeError.
    """
    try:
        import imageio
        import numpy as np

        buf = io.BytesIO()
        writer = imageio.get_writer(buf, format='mp4', fps=fps, quality=7, macro_block_size=None)
        for frame in frames:
            writer.append_data(np.array(frame.convert("RGB")))
        writer.close()
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        raise RuntimeError(
            f"MP4 генерация недоступна (нужен ffmpeg и imageio[ffmpeg]): {e}"
        )


# ─────────────────────────────────────────────
#  ЕДИНЫЙ ИНТЕРФЕЙС
# ─────────────────────────────────────────────

def render_output(
    emoji_img: Image.Image,
    settings: dict,
    custom_bg: Optional[Image.Image] = None,
    preview_only: bool = False,
) -> Tuple[bytes, str]:
    """
    Высокоуровневый метод: генерирует вывод по настройкам.
    Возвращает (file_bytes, mime_type).

    preview_only=True → всегда PNG (1 кадр, бесплатно).
    """
    out_format = settings.get("out_format", "GIF").upper()

    if preview_only:
        frames = generate_frames(emoji_img, settings, custom_bg, animated=False)
        return save_png_bytes(frames[0]), "image/png"

    if out_format == "PNG":
        frames = generate_frames(emoji_img, settings, custom_bg, animated=False)
        return save_png_bytes(frames[0]), "image/png"

    elif out_format == "MP4":
        frames = generate_frames(emoji_img, settings, custom_bg, animated=True)
        return save_mp4_bytes(frames), "video/mp4"

    else:  # GIF (default)
        frames = generate_frames(emoji_img, settings, custom_bg, animated=True)
        return save_gif_bytes(frames), "image/gif"
