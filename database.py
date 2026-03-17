"""
database.py — работа с SQLite базой данных
"""
import sqlite3
from datetime import datetime
from config import DB_PATH


# ─────────────────────────────────────────────
#  СОЕДИНЕНИЕ
# ─────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────
#  ИНИЦИАЛИЗАЦИЯ СХЕМЫ
# ─────────────────────────────────────────────
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        -- Пользователи
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username    TEXT,
            full_name   TEXT,
            balance     REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            conversions INTEGER DEFAULT 0,
            reg_date    TEXT NOT NULL,
            referrer_id INTEGER DEFAULT NULL,
            is_banned   INTEGER DEFAULT 0
        );

        -- Настройки пользователя для генерации
        CREATE TABLE IF NOT EXISTS user_settings (
            telegram_id   INTEGER PRIMARY KEY,
            bg_color      TEXT    DEFAULT '#1a1a2e',
            emoji_color   TEXT    DEFAULT '',
            resolution    TEXT    DEFAULT '1920x530',
            out_format    TEXT    DEFAULT 'GIF',
            custom_media  TEXT    DEFAULT NULL,
            notes         TEXT    DEFAULT '',
            wm_text       TEXT    DEFAULT '',
            wm_font       TEXT    DEFAULT 'default',
            wm_color      TEXT    DEFAULT '#ffffff',
            wm_position   TEXT    DEFAULT 'bottom_right',
            wm_opacity    REAL    DEFAULT 0.7,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );

        -- История конвертаций
        CREATE TABLE IF NOT EXISTS conversions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            out_type    TEXT    NOT NULL,
            cost        REAL    DEFAULT 5.0,
            created_at  TEXT    NOT NULL
        );

        -- Платежи (пополнение баланса)
        CREATE TABLE IF NOT EXISTS payments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id  INTEGER NOT NULL,
            amount       REAL    NOT NULL,
            method       TEXT    NOT NULL,
            status       TEXT    DEFAULT 'pending',
            invoice_id   TEXT,
            receipt_file TEXT,
            created_at   TEXT    NOT NULL
        );

        -- Реферальные связи
        CREATE TABLE IF NOT EXISTS referrals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            user_id     INTEGER NOT NULL UNIQUE
        );

        -- Кастомные эмодзи / стикеры от другого бота
        CREATE TABLE IF NOT EXISTS custom_emoji (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            file_id     TEXT    NOT NULL UNIQUE,
            file_type   TEXT    NOT NULL DEFAULT 'sticker',
            added_by    INTEGER NOT NULL,
            created_at  TEXT    NOT NULL
        );

        -- Глобальные настройки бота (для админки)
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()

    # Миграции (добавляем колонки если их нет)
    _safe_alter(conn, "users", "is_banned", "INTEGER DEFAULT 0")
    _safe_alter(conn, "users", "conversions", "INTEGER DEFAULT 0")

    conn.close()


def _safe_alter(conn, table, column, definition):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()
    except Exception:
        pass


# ─────────────────────────────────────────────
#  ПОЛЬЗОВАТЕЛИ
# ─────────────────────────────────────────────
def db_get_user(telegram_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()


def db_create_user(telegram_id: int, username: str, full_name: str, referrer_id=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users "
            "(telegram_id, username, full_name, reg_date, referrer_id) VALUES (?,?,?,?,?)",
            (telegram_id, username, full_name, now, referrer_id)
        )
        conn.commit()
    return db_get_user(telegram_id)


def db_get_or_create_user(telegram_id: int, username: str = "", full_name: str = "", referrer_id=None):
    u = db_get_user(telegram_id)
    return u if u else db_create_user(telegram_id, username, full_name, referrer_id)


def db_update_balance(telegram_id: int, delta: float):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id=?",
            (delta, telegram_id)
        )
        conn.commit()


def db_get_balance(telegram_id: int) -> float:
    u = db_get_user(telegram_id)
    return float(u["balance"]) if u else 0.0


def db_increment_conversions(telegram_id: int, cost: float):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET conversions=conversions+1, total_spent=total_spent+? "
            "WHERE telegram_id=?",
            (cost, telegram_id)
        )
        conn.commit()


def db_all_users():
    with get_db() as conn:
        return conn.execute("SELECT * FROM users").fetchall()


def db_ban_user(telegram_id: int, ban: bool = True):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_banned=? WHERE telegram_id=?",
            (1 if ban else 0, telegram_id)
        )
        conn.commit()


# ─────────────────────────────────────────────
#  НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ
# ─────────────────────────────────────────────
def db_get_settings(telegram_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
    if row:
        return dict(row)
    # Дефолтные настройки
    defaults = {
        "telegram_id":  telegram_id,
        "bg_color":     "#1a1a2e",
        "emoji_color":  "",
        "resolution":   "1920x530",
        "out_format":   "GIF",
        "custom_media": None,
        "notes":        "",
        "wm_text":      "",
        "wm_font":      "default",
        "wm_color":     "#ffffff",
        "wm_position":  "bottom_right",
        "wm_opacity":   0.7,
    }
    _db_upsert_settings(telegram_id, defaults)
    return defaults


def _db_upsert_settings(telegram_id: int, data: dict):
    fields = ["bg_color","emoji_color","resolution","out_format","custom_media",
              "notes","wm_text","wm_font","wm_color","wm_position","wm_opacity"]
    with get_db() as conn:
        existing = conn.execute(
            "SELECT telegram_id FROM user_settings WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        if existing:
            updates = ", ".join(f"{f}=?" for f in fields if f in data)
            vals = [data[f] for f in fields if f in data]
            vals.append(telegram_id)
            if updates:
                conn.execute(f"UPDATE user_settings SET {updates} WHERE telegram_id=?", vals)
        else:
            conn.execute(
                "INSERT OR IGNORE INTO user_settings (telegram_id) VALUES (?)", (telegram_id,)
            )
            updates = ", ".join(f"{f}=?" for f in fields if f in data)
            vals = [data[f] for f in fields if f in data]
            vals.append(telegram_id)
            if updates:
                conn.execute(f"UPDATE user_settings SET {updates} WHERE telegram_id=?", vals)
        conn.commit()


def db_set_setting_field(telegram_id: int, field: str, value):
    _db_upsert_settings(telegram_id, {field: value})


# ─────────────────────────────────────────────
#  ПЛАТЕЖИ
# ─────────────────────────────────────────────
def db_create_payment(telegram_id: int, amount: float, method: str, invoice_id: str = None) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO payments (telegram_id, amount, method, status, invoice_id, created_at) "
            "VALUES (?,?,?,'pending',?,?)",
            (telegram_id, amount, method, invoice_id, now)
        )
        conn.commit()
        return cur.lastrowid


def db_confirm_payment(payment_id: int, receipt_file: str = None):
    with get_db() as conn:
        conn.execute(
            "UPDATE payments SET status='paid', receipt_file=? WHERE id=?",
            (receipt_file, payment_id)
        )
        conn.commit()


def db_get_payment(payment_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE id=?", (payment_id,)
        ).fetchone()


def db_get_payments_pending():
    with get_db() as conn:
        return conn.execute(
            "SELECT p.*, u.username, u.full_name FROM payments p "
            "JOIN users u ON u.telegram_id=p.telegram_id "
            "WHERE p.status='pending' ORDER BY p.created_at DESC"
        ).fetchall()


# ─────────────────────────────────────────────
#  КОНВЕРТАЦИИ
# ─────────────────────────────────────────────
def db_log_conversion(telegram_id: int, out_type: str, cost: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversions (telegram_id, out_type, cost, created_at) VALUES (?,?,?,?)",
            (telegram_id, out_type, cost, now)
        )
        conn.commit()
    db_increment_conversions(telegram_id, cost)


# ─────────────────────────────────────────────
#  РЕФЕРАЛЬНАЯ ПРОГРАММА
# ─────────────────────────────────────────────
def db_add_referral(referrer_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO referrals (referrer_id, user_id) VALUES (?,?)",
            (referrer_id, user_id)
        )
        conn.commit()


def db_count_referrals(telegram_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=?", (telegram_id,)
        ).fetchone()
    return row["cnt"] if row else 0


# ─────────────────────────────────────────────
#  КАСТОМНЫЕ ЭМОДЗИ
# ─────────────────────────────────────────────
def db_add_custom_emoji(name: str, file_id: str, file_type: str, added_by: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO custom_emoji (name, file_id, file_type, added_by, created_at) "
            "VALUES (?,?,?,?,?)",
            (name, file_id, file_type, added_by, now)
        )
        conn.commit()


def db_get_custom_emoji(limit: int = 20, offset: int = 0):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM custom_emoji ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()


def db_delete_custom_emoji(emoji_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM custom_emoji WHERE id=?", (emoji_id,))
        conn.commit()


def db_count_custom_emoji() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM custom_emoji").fetchone()
    return row["cnt"] if row else 0


# ─────────────────────────────────────────────
#  ГЛОБАЛЬНЫЕ НАСТРОЙКИ (admin)
# ─────────────────────────────────────────────
def db_get_global(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def db_set_global(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value)
        )
        conn.commit()


def db_del_global(key: str):
    with get_db() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))
        conn.commit()


# ─────────────────────────────────────────────
#  СТАТИСТИКА
# ─────────────────────────────────────────────
def db_stats() -> dict:
    with get_db() as conn:
        users_total = conn.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"]
        active_today = conn.execute(
            "SELECT COUNT(*) as n FROM conversions WHERE created_at >= date('now')"
        ).fetchone()["n"]
        revenue_total = conn.execute(
            "SELECT COALESCE(SUM(cost),0) as s FROM conversions"
        ).fetchone()["s"]
        pending_payments = conn.execute(
            "SELECT COUNT(*) as n FROM payments WHERE status='pending'"
        ).fetchone()["n"]
    return {
        "users":    users_total,
        "active":   active_today,
        "revenue":  revenue_total,
        "pending":  pending_payments,
    }
