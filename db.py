import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

DATABASE_URL=os.getenv("DATABASE_URL","").strip()
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
AUTODB_PATH=os.path.join(BASE_DIR,"data","javDbs.db")
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc: raise RuntimeError("Package psycopg[binary] belum terpasang") from exc

def _require_db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL belum diset")

@contextmanager
def db():
    _require_db();conn=psycopg.connect(DATABASE_URL,row_factory=dict_row,autocommit=False)
    try: yield conn;conn.commit()
    except Exception: conn.rollback();raise
    finally: conn.close()

def _json(v:Any): return v.isoformat() if isinstance(v,datetime) else v

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,code TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',progress INTEGER NOT NULL DEFAULT 0,stage TEXT NOT NULL DEFAULT 'Queued',message TEXT NOT NULL DEFAULT '',size_bytes BIGINT NOT NULL DEFAULT 0,speed_kbps DOUBLE PRECISION NOT NULL DEFAULT 0,result JSONB,meta JSONB NOT NULL DEFAULT '{}'::jsonb,error TEXT,session_token TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),completed_at TIMESTAMPTZ)""")
        conn.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("""CREATE TABLE IF NOT EXISTS task_logs(id BIGSERIAL PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,level TEXT NOT NULL DEFAULT 'info',message TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id,id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS histories(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL DEFAULT '',session_token TEXT NOT NULL DEFAULT '',drive_file_id TEXT,thumb TEXT,data JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_histories_email ON histories(email,created_at DESC)")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions(session_token TEXT PRIMARY KEY,email TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS automations(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,enabled BOOLEAN NOT NULL DEFAULT TRUE,interval_minutes INTEGER NOT NULL DEFAULT 60,action TEXT NOT NULL DEFAULT 'worker',config JSONB NOT NULL DEFAULT '{}'::jsonb,last_run_at TIMESTAMPTZ,next_run_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.execute("ALTER TABLE automations ADD COLUMN IF NOT EXISTS interval_minutes INTEGER NOT NULL DEFAULT 60")

def create_task(task_id:str,code:str,session_token:Optional[str]=None,meta:Optional[dict]=None):
    with db() as conn:
        conn.execute("""INSERT INTO tasks(task_id,code,status,progress,stage,message,session_token,meta) VALUES(%s,%s,'queued',0,'Queued','Menunggu GitHub Actions...',%s,%s::jsonb) ON CONFLICT(task_id) DO UPDATE SET code=EXCLUDED.code,session_token=EXCLUDED.session_token,meta=EXCLUDED.meta,updated_at=NOW()""",(task_id,code,session_token,json.dumps(meta or {},ensure_ascii=False)))
        conn.execute("INSERT INTO task_logs(task_id,message) VALUES(%s,%s)",(task_id,f"Menerima input: {code}"))

def update_task(task_id:str,**fields):
    allowed={"status","progress","stage","message","size_bytes","speed_kbps","result","error","completed_at","session_token","meta"};fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:return
    fields["updated_at"]=datetime.now(timezone.utc);parts=[f"{k}=%s"+("::jsonb" if k in {"result","meta"} else "") for k in fields];vals=[json.dumps(v,ensure_ascii=False) if k in {"result","meta"} else v for k,v in fields.items()]+[task_id]
    with db() as conn:conn.execute(f"UPDATE tasks SET {','.join(parts)} WHERE task_id=%s",vals)

def add_log(task_id:str,message:str,level:str="info"):
    with db() as conn:
        conn.execute("INSERT INTO task_logs(task_id,level,message) VALUES(%s,%s,%s)",(task_id,level,message));conn.execute("UPDATE tasks SET updated_at=NOW() WHERE task_id=%s",(task_id,))

def get_logs(task_id:str,limit:int=200):
    with db() as conn:rows=conn.execute("SELECT level,message,created_at FROM task_logs WHERE task_id=%s ORDER BY id ASC LIMIT %s",(task_id,limit)).fetchall()
    return [{"level":r["level"],"message":r["message"],"created_at":_json(r["created_at"])} for r in rows]

def get_task(task_id:str):
    with db() as conn:row=conn.execute("SELECT * FROM tasks WHERE task_id=%s",(task_id,)).fetchone()
    if not row:return None
    row=dict(row);row["logs"]=get_logs(task_id);return {k:_json(v) for k,v in row.items()}

def upsert_session(session_token:str,email:str):
    with db() as conn:conn.execute("INSERT INTO sessions(session_token,email) VALUES(%s,%s) ON CONFLICT(session_token) DO UPDATE SET email=EXCLUDED.email,updated_at=NOW()",(session_token,email or ""))

def get_session_email(session_token:str)->str:
    with db() as conn:row=conn.execute("SELECT email FROM sessions WHERE session_token=%s",(session_token,)).fetchone()
    return (row["email"] if row else "") or ""

def upsert_history(item:dict):
    name=item.get("name","");email=item.get("email","") or "";session=item.get("session_token","") or "";data=dict(item)
    for k in ("email","session_token","name","drive_file_id","thumb"):data.pop(k,None)
    with db() as conn:
        conn.execute("DELETE FROM histories WHERE name=%s AND (email=%s OR session_token=%s)",(name,email,session))
        conn.execute("INSERT INTO histories(name,email,session_token,drive_file_id,thumb,data) VALUES(%s,%s,%s,%s,%s,%s::jsonb)",(name,email,session,item.get("drive_file_id"),item.get("thumb"),json.dumps(data,ensure_ascii=False)))

def list_history(session_token:str="",email:str="",limit:int=50):
    with db() as conn:
        if session_token:
            rows=conn.execute("SELECT name,email,session_token,drive_file_id,thumb,data FROM histories WHERE session_token=%s OR (%s<>'' AND email=%s) ORDER BY created_at DESC LIMIT %s",(session_token,email,email,limit)).fetchall()
        elif email:
            rows=conn.execute("SELECT name,email,session_token,drive_file_id,thumb,data FROM histories WHERE email=%s ORDER BY created_at DESC LIMIT %s",(email,limit)).fetchall()
        else:
            rows=conn.execute("SELECT name,email,session_token,drive_file_id,thumb,data FROM histories ORDER BY created_at DESC LIMIT %s",(limit,)).fetchall()
    out=[]
    for r in rows:
        item=dict(r["data"] or {});item.update(name=r["name"],email=r["email"],session_token=r["session_token"])
        if r["drive_file_id"]:item["drive_file_id"]=r["drive_file_id"]
        if r["thumb"]:item["thumb"]=r["thumb"]
        out.append(item)
    return out

def delete_history(name:str,session_token:str=""):
    with db() as conn:
        if session_token:conn.execute("DELETE FROM histories WHERE name=%s AND session_token=%s",(name,session_token))
        else:conn.execute("DELETE FROM histories WHERE name=%s",(name,))

def clear_history(session_token:str=""):
    with db() as conn:
        if session_token:conn.execute("DELETE FROM histories WHERE session_token=%s",(session_token,))
        else:conn.execute("DELETE FROM histories")

def find_history_duplicate(code:str,email:str):
    needle="".join(c for c in code if c.isalnum()).lower()
    if not needle:return None
    for item in list_history(email=email,limit=200):
        norm="".join(c for c in item.get("name","") if c.isalnum()).lower()
        if norm and needle in norm:return item
    return None

def db_check():
    """Cek apakah semua tabel utama terload — kembalikan status + jumlah baris per tabel."""
    checks={
        "tasks":"SELECT COUNT(*) AS c FROM tasks",
        "task_logs":"SELECT COUNT(*) AS c FROM task_logs",
        "histories":"SELECT COUNT(*) AS c FROM histories",
        "sessions":"SELECT COUNT(*) AS c FROM sessions",
        "automations":"SELECT COUNT(*) AS c FROM automations",
    }
    status,ok={},True
    for name,sql in checks.items():
        try:
            with db() as conn:
                row=conn.execute(sql).fetchone()
            status[name]={"loaded":True,"rows":(row["c"] if row else 0)}
        except Exception as e:
            status[name]={"loaded":False,"error":str(e)}
            ok=False
    return status,ok

def _autodb():
    """Buka automation database (SQLite javDbs.db) secara read-only."""
    if not os.path.exists(AUTODB_PATH):
        raise RuntimeError(f"Automation DB tidak ditemukan: {AUTODB_PATH}")
    con=sqlite3.connect(f"file:{AUTODB_PATH}?mode=ro",uri=True,check_same_thread=False)
    con.row_factory=sqlite3.Row
    return con

def autodb_status():
    """Cek apakah seluruh database/tabel dalam automation DB (javDbs.db) terload."""
    dbs,ok={},True
    try:
        con=_autodb();cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables=[r[0] for r in cur.fetchall()]
        integ=None
        try: integ=cur.execute("PRAGMA integrity_check").fetchone()[0]
        except Exception as e: integ=f"error:{e}";ok=False
        for t in tables:
            try:
                cnt=cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                dbs[t]={"loaded":True,"rows":cnt}
            except Exception as e:
                dbs[t]={"loaded":False,"error":str(e)};ok=False
        con.close()
        return {"databases":{"javDbs.db":{"loaded":ok,"tables":dbs,"integrity_check":integ}}},ok
    except Exception as e:
        return {"databases":{"javDbs.db":{"loaded":False,"error":str(e)}}},False

def search_automations(q:str="",limit:int=50):
    """Cari di automation DB (javDbs.db → search_logs): cocok dengan video_id/title/keywords."""
    needle=(q or "").strip().lower()
    if not needle:return []
    like=f"%{needle}%"
    out=[]
    try:
        con=_autodb();cur=con.cursor()
        cur.execute("""SELECT video_id,title,actress,direktori,video_url,thumbnail FROM (
            SELECT video_id,title,actress,direktori,video_url,thumbnail,0 AS prio
              FROM search_logs WHERE lower(video_id) LIKE ?
            UNION ALL
            SELECT video_id,title,actress,direktori,video_url,thumbnail,1 AS prio
              FROM search_logs
             WHERE (lower(title) LIKE ? OR lower(coalesce(keywords,'')) LIKE ?)
               AND lower(video_id) NOT LIKE ?
            ) t ORDER BY prio ASC, video_id ASC LIMIT ?""",(like,like,like,like,limit))
        for r in cur.fetchall():
            vid,title,actress,direktori,url,thumb=r
            out.append({"name":vid,"code":vid,"id":vid,"title":title,"url":url,"thumb":thumb})
        con.close()
    except Exception:
        out=[]
    return out

def list_automations():
    with db() as conn:rows=conn.execute("SELECT * FROM automations ORDER BY id DESC").fetchall()
    return [{k:_json(v) for k,v in dict(r).items()} for r in rows]

def upsert_automation(name:str,interval_minutes:int=60,action:str="worker",config:Optional[dict]=None,enabled:bool=True):
    interval_minutes=max(1,int(interval_minutes))
    with db() as conn:row=conn.execute("""INSERT INTO automations(name,enabled,interval_minutes,action,config) VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(name) DO UPDATE SET enabled=EXCLUDED.enabled,interval_minutes=EXCLUDED.interval_minutes,action=EXCLUDED.action,config=EXCLUDED.config,updated_at=NOW() RETURNING id""",(name,enabled,interval_minutes,action,json.dumps(config or {}))).fetchone()
    return row["id"]

def due_automations():
    with db() as conn:rows=conn.execute("SELECT * FROM automations WHERE enabled=TRUE AND (last_run_at IS NULL OR last_run_at+make_interval(mins=>interval_minutes)<=NOW()) ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]

def mark_automation_run(automation_id:int):
    with db() as conn:conn.execute("UPDATE automations SET last_run_at=NOW(),next_run_at=NOW()+make_interval(mins=>interval_minutes),updated_at=NOW() WHERE id=%s",(automation_id,))
