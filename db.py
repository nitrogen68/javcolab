import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL belum diset. Tambahkan DATABASE_URL pada environment Vercel dan GitHub Actions.")

try:
    import psycopg
except ImportError as exc:
    raise RuntimeError("Package psycopg belum terpasang. Tambahkan psycopg[binary] ke requirements.txt") from exc


def utcnow():
    return datetime.now(timezone.utc)


@contextmanager
def db():
    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'Queued',
            message TEXT NOT NULL DEFAULT '',
            size_bytes BIGINT NOT NULL DEFAULT 0,
            speed_kbps DOUBLE PRECISION NOT NULL DEFAULT 0,
            result JSONB,
            error TEXT,
            session_token TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS task_logs (
            id BIGSERIAL PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
            level TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id, id)")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS automations (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            schedule TEXT,
            action TEXT NOT NULL DEFAULT 'worker',
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_run_at TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """)


def create_task(task_id: str, code: str, session_token: Optional[str] = None):
    with db() as conn:
        conn.execute("""
        INSERT INTO tasks(task_id, code, status, progress, stage, message, session_token)
        VALUES (%s, %s, 'queued', 0, 'Queued', 'Menunggu GitHub Actions...', %s)
        ON CONFLICT(task_id) DO UPDATE SET code=EXCLUDED.code, session_token=EXCLUDED.session_token,
          updated_at=NOW()
        """, (task_id, code, session_token))
        conn.execute("INSERT INTO task_logs(task_id, message) VALUES (%s, %s)", (task_id, f"Menerima input: {code}"))


def update_task(task_id: str, **fields):
    allowed = {"status", "progress", "stage", "message", "size_bytes", "speed_kbps", "result", "error", "completed_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = utcnow()
    parts = []
    values = []
    for k, v in fields.items():
        parts.append(f"{k} = %s")
        values.append(v)
    values.append(task_id)
    with db() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(parts)} WHERE task_id = %s", values)


def add_log(task_id: str, message: str, level: str = "info"):
    with db() as conn:
        conn.execute("INSERT INTO task_logs(task_id, level, message) VALUES (%s, %s, %s)", (task_id, level, message))
        conn.execute("UPDATE tasks SET updated_at=NOW() WHERE task_id=%s", (task_id,))


def get_task(task_id: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id=%s", (task_id,)).fetchone()
        if not row:
            return None
        cols = [d.name for d in conn.execute("SELECT * FROM tasks WHERE FALSE").description]
        return dict(zip(cols, row))


def get_logs(task_id: str, limit: int = 100):
    with db() as conn:
        rows = conn.execute("SELECT level, message, created_at FROM task_logs WHERE task_id=%s ORDER BY id ASC LIMIT %s", (task_id, limit)).fetchall()
        return [{"level": r[0], "message": r[1], "created_at": r[2].isoformat()} for r in rows]


def list_tasks(limit: int = 100):
    with db() as conn:
        rows = conn.execute("SELECT task_id, code, status, progress, stage, message, size_bytes, speed_kbps, result, error, created_at, updated_at, completed_at FROM tasks ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
        cols = ["task_id", "code", "status", "progress", "stage", "message", "size_bytes", "speed_kbps", "result", "error", "created_at", "updated_at", "completed_at"]
        return [{k: _json_value(v) for k, v in zip(cols, r)} for r in rows]


def _json_value(v: Any):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def list_automations():
    with db() as conn:
        rows = conn.execute("SELECT id, name, enabled, schedule, action, config, last_run_at, next_run_at, created_at, updated_at FROM automations ORDER BY id DESC").fetchall()
        cols = ["id", "name", "enabled", "schedule", "action", "config", "last_run_at", "next_run_at", "created_at", "updated_at"]
        return [{k: _json_value(v) for k, v in zip(cols, r)} for r in rows]


def upsert_automation(name: str, schedule: str, action: str = "worker", config: Optional[dict] = None, enabled: bool = True):
    import json
    with db() as conn:
        row = conn.execute("SELECT id FROM automations WHERE name=%s", (name,)).fetchone()
        if row:
            conn.execute("UPDATE automations SET schedule=%s, action=%s, config=%s::jsonb, enabled=%s, updated_at=NOW() WHERE id=%s", (schedule, action, json.dumps(config or {}), enabled, row[0]))
            return row[0]
        row = conn.execute("INSERT INTO automations(name, schedule, action, config, enabled) VALUES(%s,%s,%s,%s::jsonb,%s) RETURNING id", (name, schedule, action, json.dumps(config or {}), enabled)).fetchone()
        return row[0]
