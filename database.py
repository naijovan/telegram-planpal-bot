import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS drafts (
        user_id INTEGER PRIMARY KEY,
        stage TEXT,
        data TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS saved_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        google_event_id TEXT,
        title TEXT,
        event_date TEXT,
        start_time TEXT,
        end_time TEXT,
        location TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    c.execute("PRAGMA table_info(saved_events)")
    columns = {row["name"] for row in c.fetchall()}
    if "google_event_id" not in columns:
        c.execute("ALTER TABLE saved_events ADD COLUMN google_event_id TEXT")
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS important_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_date TEXT,
        title TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """
    )
    c.execute(
        """
    CREATE TABLE IF NOT EXISTS task_pins (
        user_id INTEGER,
        chat_id INTEGER,
        task_date TEXT,
        pinned_message_id INTEGER,
        google_calendar_event_id TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, chat_id, task_date)
    )
    """
    )
    conn.commit()
    conn.close()


def save_draft(user_id: int, stage: str, data: dict) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO drafts (user_id, stage, data)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET stage=excluded.stage, data=excluded.data, updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, stage, json.dumps(data)),
    )
    conn.commit()
    conn.close()


def get_draft(user_id: int) -> dict | None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT stage, data FROM drafts WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"stage": row["stage"], "data": json.loads(row["data"])}


def clear_draft(user_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_event(user_id: int, event_data: dict) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO saved_events (
            user_id, google_event_id, title, event_date, start_time, end_time, location, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            event_data.get("google_event_id"),
            event_data.get("title"),
            event_data.get("date"),
            event_data.get("start_time"),
            event_data.get("end_time"),
            event_data.get("location"),
            event_data.get("notes"),
        ),
    )
    event_id = c.lastrowid
    conn.commit()
    conn.close()
    return event_id


def list_events(user_id: int, event_date: str) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, google_event_id, title, event_date, start_time, end_time, location, notes FROM saved_events "
        "WHERE user_id = ? AND event_date = ? ORDER BY start_time",
        (user_id, event_date),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_event(user_id: int, event_id: int) -> dict | None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, google_event_id, title, event_date as date, start_time, end_time, location, notes "
        "FROM saved_events WHERE user_id = ? AND id = ?",
        (user_id, event_id),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def update_event(event_id: int, fields: dict) -> None:
    # Only allow updating known columns
    allowed = {
        "title": "title",
        "date": "event_date",
        "event_date": "event_date",
        "start_time": "start_time",
        "end_time": "end_time",
        "location": "location",
        "notes": "notes",
        "google_event_id": "google_event_id",
    }
    updates = []
    params = []
    for key, val in fields.items():
        col = allowed.get(key)
        if not col:
            continue
        updates.append(f"{col} = ?")
        params.append(val)
    if not updates:
        return
    params.append(event_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE saved_events SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def delete_event(event_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM saved_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def delete_event_by_google_id(google_event_id: str) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM saved_events WHERE google_event_id = ?", (google_event_id,))
    conn.commit()
    conn.close()


def add_important_task(user_id: int, task_date: str, title: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO important_tasks (user_id, task_date, title, status)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, task_date, title, "pending"),
    )
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return task_id


def list_important_tasks(user_id: int, task_date: str) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, task_date, title, status, created_at, completed_at
        FROM important_tasks
        WHERE user_id = ? AND task_date = ?
        ORDER BY
            CASE status WHEN 'pending' THEN 0 ELSE 1 END,
            created_at,
            id
        """,
        (user_id, task_date),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_important_task(user_id: int, task_id: int) -> dict | None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, task_date, title, status, created_at, completed_at
        FROM important_tasks
        WHERE user_id = ? AND id = ?
        """,
        (user_id, task_id),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def mark_important_task_done(user_id: int, task_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE important_tasks
        SET status = 'done', completed_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND id = ?
        """,
        (user_id, task_id),
    )
    conn.commit()
    conn.close()


def update_important_task_title(user_id: int, task_id: int, title: str) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE important_tasks SET title = ? WHERE user_id = ? AND id = ?",
        (title, user_id, task_id),
    )
    conn.commit()
    conn.close()


def delete_important_task(user_id: int, task_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM important_tasks WHERE user_id = ? AND id = ?", (user_id, task_id))
    conn.commit()
    conn.close()


def get_task_pin(user_id: int, chat_id: int, task_date: str) -> dict | None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, task_date, pinned_message_id, google_calendar_event_id, updated_at
        FROM task_pins
        WHERE user_id = ? AND chat_id = ? AND task_date = ?
        """,
        (user_id, chat_id, task_date),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def list_task_pins(user_id: int, chat_id: int) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, task_date, pinned_message_id, google_calendar_event_id, updated_at
        FROM task_pins
        WHERE user_id = ? AND chat_id = ?
        ORDER BY task_date ASC
        """,
        (user_id, chat_id),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_task_pin(
    user_id: int,
    chat_id: int,
    task_date: str,
    pinned_message_id: int | None,
    google_calendar_event_id: str | None = None,
) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO task_pins (
            user_id, chat_id, task_date, pinned_message_id, google_calendar_event_id
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, chat_id, task_date) DO UPDATE SET
            pinned_message_id = excluded.pinned_message_id,
            google_calendar_event_id = COALESCE(excluded.google_calendar_event_id, task_pins.google_calendar_event_id),
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, chat_id, task_date, pinned_message_id, google_calendar_event_id),
    )
    conn.commit()
    conn.close()


def update_task_pin_google_event_id(
    user_id: int,
    chat_id: int,
    task_date: str,
    google_calendar_event_id: str | None,
) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE task_pins
        SET google_calendar_event_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND chat_id = ? AND task_date = ?
        """,
        (google_calendar_event_id, user_id, chat_id, task_date),
    )
    conn.commit()
    conn.close()


def list_task_pins_before(user_id: int, chat_id: int, before_date: str) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, task_date, pinned_message_id, google_calendar_event_id, updated_at
        FROM task_pins
        WHERE user_id = ? AND chat_id = ? AND task_date < ?
        ORDER BY task_date ASC
        """,
        (user_id, chat_id, before_date),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_old_task_pins_if_needed(user_id: int, chat_id: int, before_date: str) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "DELETE FROM task_pins WHERE user_id = ? AND chat_id = ? AND task_date < ?",
        (user_id, chat_id, before_date),
    )
    conn.commit()
    conn.close()
