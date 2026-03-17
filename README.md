# 🎨 Emoji GIF Generator Bot

Telegram-бот на aiogram 3.x, превращающий эмодзи и стикеры в GIF / PNG / MP4
с умной HSV-перекраской, вотермаркой, балансом и админ-панелью.

---

## 📁 Структура проекта

```
bot/
├── bot.py               — точка входа, поллинг
├── config.py            — настройки из .env
├── database.py          — SQLite (WAL), все запросы
├── states.py            — FSM-состояния
├── keyboards.py         — все inline/reply клавиатуры
├── image_processor.py   — загрузка эмодзи, HSV-перекраска, вотермарка
├── gif_generator.py     — сборка кадров, сохранение GIF/PNG/MP4
├── handlers/
│   ├── start.py         — /start, /help, профиль
│   ├── settings.py      — меню настроек (цвет, разрешение, формат…)
│   ├── watermark.py     — подменю вотермарки
│   ├── media_handler.py — приём эмодзи/стикеров/фото, генерация
│   ├── payment.py       — CryptoBot + карта, пополнение баланса
│   └── admin.py         — статистика, юзеры, рассылка, кастом-эмодзи
├── fonts/               — сюда кладёшь свои .ttf / .otf
├── temp/                — временные файлы (автоочищаются)
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## ⚙️ Быстрый старт (локально)

```bash
# 1. Клонировать / скопировать папку bot/
cd bot

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Создать .env из примера
cp .env.example .env
# Открыть .env и вписать BOT_TOKEN, ADMIN_IDS, CRYPTOBOT_TOKEN, реквизиты

# 5. Запустить
python bot.py
```

---

## 🐳 Docker

```bash
# Сборка образа
docker build -t emoji-gif-bot .

# Запуск (БД и temp хранятся на хосте)
docker run -d \
  --name emoji-bot \
  --env-file .env \
  -v $(pwd)/database.db:/app/database.db \
  -v $(pwd)/temp:/app/temp \
  -v $(pwd)/fonts:/app/fonts \
  emoji-gif-bot
```

Или через **docker-compose.yml**:

```yaml
version: "3.9"
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
    volumes:
      - ./database.db:/app/database.db
      - ./temp:/app/temp
      - ./fonts:/app/fonts
```

```bash
docker compose up -d
```

---

## 🔑 .env — все переменные

| Переменная | Описание | Пример |
|---|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather | `123:ABC...` |
| `ADMIN_IDS` | ID администраторов через запятую | `123456,789012` |
| `CRYPTOBOT_TOKEN` | Токен из @CryptoBot | `12345:AAB...` |
| `BANK_CARD` | Номер карты для ручных платежей | `4276 1234 5678 9012` |
| `BANK_NAME` | Название банка | `Сбербанк` |
| `BANK_RECEIVER` | ФИО получателя | `Иван И.` |
| `CONVERSION_PRICE` | Цена конвертации в рублях | `5.0` |
| `DB_PATH` | Путь к SQLite файлу | `database.db` |
| `TEMP_DIR` | Папка временных файлов | `temp` |
| `FONTS_DIR` | Папка со шрифтами | `fonts` |
| `TEMP_TTL_HOURS` | Через сколько часов чистить temp | `2` |
| `MAX_FRAMES` | Кадров в GIF | `60` |
| `GIF_DURATION_MS` | Длительность кадра (мс) | `17` |
| `REFERRAL_PCT` | % рефералу от пополнения | `10` |

---

## 💳 Оплата

### CryptoBot (авто)
1. Открой @CryptoBot → `/pay` → **My Apps** → **Create App**
2. Вставь токен в `CRYPTOBOT_TOKEN`
3. Бот принимает USDT, конвертирует по курсу ₽/90

### Банковская карта (полу-авто)
- Пользователь переводит на `BANK_CARD`, шлёт скриншот
- Бот пересылает скриншот всем `ADMIN_IDS`
- Администратор нажимает ✅ / ❌ → баланс зачисляется автоматически

---

## 🎨 Добавление шрифтов

Положи `.ttf` или `.otf` файлы в папку `fonts/`.
Они автоматически появятся в меню выбора шрифта для вотермарки.

---

## 👑 Кастомные эмодзи

Через **Админ → Кастомные эмодзи** добавляй стикеры/изображения с именами.
Пользователи видят их в меню **💎 Эмодзи** и могут использовать как источник.

---

## 🛠 Команды

| Команда | Описание |
|---|---|
| `/start` | Запуск, регистрация, реферальная ссылка |
| `/help` | Справка |
| `/settings` | Меню настроек |
| `/profile` | Баланс, статистика |
| `/topup` | Пополнить баланс |
| `/admin` | Админ-панель (только для ADMIN_IDS) |

---

## 📌 Примечания

- **MP4** требует `ffmpeg` в системе (`imageio[ffmpeg]`)
- **TGS-стикеры** требуют библиотеку `lottie` (опционально)
- **HSV-перекраска** требует `matplotlib` (опционально, иначе tint-режим)
- При изменении цены через админку — вступает в силу в течение 60 секунд без перезапуска
