FROM python:3.11-slim

# Системные зависимости для Pillow, imageio/ffmpeg и lottie
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        fontconfig \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала только зависимости — кэшируется отдельным слоем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Потом исходники
COPY . .

# Директории, которые монтируются как volume на хосте
RUN mkdir -p temp fonts

# Убеждаемся, что шрифты системы обновлены
RUN fc-cache -fv

CMD ["python", "bot.py"]
