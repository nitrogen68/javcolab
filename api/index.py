# api/index.py
# Remote Uploader — FastAPI untuk Vercel (UI + API + koordinasi GitHub)
# State disimpan di GitHub (data/state.json), eksekusi berat di GitHub Actions.
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.html import get_full_ui
from ui.modal import get_modals_html

app = FastAPI(title="Remote Uploader", docs_url=None, redoc_url=None)
APP_VERSION = "1.0.0 (Vercel + GitHub Actions)"

# ------------------------------------------------------------------ ENV
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")            # e.g. owner/repo
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
API_BASE = os.environ.get("API_BASE", "")          # public URL, dipakai worker
WORKER_SECRET = os.environ.get("WORKER_SECRET", "")  # dibagikan dengan workflow
GDRIVE_FOLDER = os.environ.get("GDRIVE_FOLDER", "javColab")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

_ENC = os.environ.get("API_ENC_KEY", "").encode() or hashlib.sha256(
    (os.environ.get("WORKER_SECRET", "puppeter") + "::enc").encode()
).digest()
FERNET = Fernet(base64.urlsafe_b64encode(_ENC[:32]))


# ------------------------------------------------------------------ GH helpers
def _gh_headers(extra=None, auth=True):
    h = {"Accept": "application/vnd.github+json"}
    if auth and GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    if extra:
        h.update(extra)
    return h


def gh_get(path):
    """Return (content_b64, sha) or (None, None)."""
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
        headers=_gh_headers(),
        timeout=20,
    )
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        raise RuntimeError(f"GH get {path}: {r.status_code} {r.text[:200]}")
    d = r.json()
    return d.get("content"), d.get("sha")


def gh_put(path, content_b64, message="state update"):
    c, sha = gh_get(path)
    body = {
        "message": message,
        "content": content_b64,
        "branch": GH_BRANCH,
        "committer": {"name": "puppeter-bot", "email": "puppeter@users.noreply.github.com"},
    }
    if sha:
        body["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
        headers=_gh_headers(auth=True),
        json=body,
        timeout=20,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GH put {path}: {r.status_code} {r.text[:250]}")
    return r.json().get("content", {}).get("sha")


def gh_delete(path):
    c, sha = gh_get(path)
    if not sha:
        return True
    r = requests.delete(
        f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
        headers=_gh_headers(auth=True),
        json={"message": f"delete {path}", "sha": sha, "branch": GH_BRANCH},
        timeout=20,
    )
    return r.status_code in (200, 204)


def state_get():
    b64, _ = gh_get("data/state.json")
    if not b64:
        return {"tasks": {}, "history": [], "sessions": {}}
    return json.loads(base64.b64decode(b64).decode("utf-8"))


def state_save(state):
    raw = json.dumps(state, ensure_ascii=False).encode("utf-8")
    if len(raw) > 1_000_000:
        state["tasks"] = {
            k: (dict(v, logs=v.get("logs", [])[-150:]) if isinstance(v, dict) else v)
            for k, v in state["tasks"].items()
        }
        raw = json.dumps(state, ensure_ascii=False).encode("utf-8")
    gh_put("data/state.json", base64.b64encode(raw).decode(), "auto: update state")


def dispatch_repo(event_type, payload):
    r = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/dispatches",
        headers=_gh_headers(auth=True),
        json={"event_type": event_type, "client_payload": payload},
        timeout=20,
    )
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"dispatch: {r.status_code} {r.text[:250]}")


def require_worker(req: Request):
    sec = (req.headers.get("x-worker-secret") or "").strip()
    if not WORKER_SECRET or sec != WORKER_SECRET:
        raise HTTPException(status_code=401, detail="X-Worker-Secret salah")


def wib_time():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y %H:%M WIB")


# ------------------------------------------------------------------ GDrive token store
TOKEN_DIR = "data/tokens"


def save_token(session_token, token_json):
    data = json.dumps(token_json).encode()
    enc = FERNET.encrypt(data)
    gh_put(f"{TOKEN_DIR}/{session_token}.enc", base64.b64encode(enc).decode(), "auto: token")


def load_token(session_token):
    b64, _ = gh_get(f"{TOKEN_DIR}/{session_token}.enc")
    if not b64:
        return None
    try:
        dec = FERNET.decrypt(base64.b64decode(b64))
        return json.loads(dec.decode("utf-8"))
    except InvalidToken:
        return None


def session_email(session_token, state=None):
    st = state if state is not None else state_get()
    return st.get("sessions", {}).get(session_token, "")


def gdrive_service(session_token):
    token = load_token(session_token)
    if not token:
        raise HTTPException(status_code=404, detail="Sesi tidak terhubung")
    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token.get("client_id") or GOOGLE_CLIENT_ID,
        client_secret=token.get("client_secret") or GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    if creds.expired:
        creds.refresh(GoogleRequest())
        token["access_token"] = creds.token
        save_token(session_token, token)
    return build("drive", "v3", credentials=creds)


def gdrive_delete_file(session_token, drive_file_id):
    try:
        if not drive_file_id:
            return False
        service = gdrive_service(session_token)
        service.files().delete(fileId=drive_file_id).execute()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ Device flow (stateless via GH pending)
PENDING_DIR = "data/pending"


def pending_save(device_code, obj):
    gh_put(
        f"{PENDING_DIR}/{device_code}.json",
        base64.b64encode(json.dumps(obj).encode()).decode(),
        "auto: pending auth",
    )


def pending_load(device_code):
    b64, sha = gh_get(f"{PENDING_DIR}/{device_code}.json")
    if not b64:
        return None, None
    return json.loads(base64.b64decode(b64).decode()), sha


def pending_del(device_code):
    gh_delete(f"{PENDING_DIR}/{device_code}.json")


@app.get("/api/health")
def health():
    return {"ok": True, "app": APP_VERSION}


# ------------------------------------------------------------------ Saran
@app.get("/api/saran_random")
def get_saran_random():
    try:
        import random
        b64, _ = gh_get("data/suggestions.json")
        if not b64:
            return []
        rows = json.loads(base64.b64decode(b64).decode())
        return [r.get("id") for r in random.sample(rows, min(5, len(rows))) if r.get("id")]
    except Exception:
        return []


# ------------------------------------------------------------------ Auth GDrive
@app.get("/api/auth/status")
def api_auth_status(session_token: str = ""):
    if not session_token:
        return {"connected": False}
    email = session_email(session_token)
    if email:
        return {"connected": True, "email": email}
    token = load_token(session_token)
    if not token:
        return {"connected": False}
    try:
        service = build("drive", "v3", credentials=gdrive_service(session_token))
        about = service.about().get(fields="user(emailAddress)").execute()
        email = about["user"]["emailAddress"]
        st = state_get()
        st.setdefault("sessions", {})[session_token] = email
        state_save(st)
        return {"connected": True, "email": email}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.post("/api/auth/device")
def api_start_device_flow():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID belum di-set")
    resp = requests.post(
        "https://oauth2.googleapis.com/device/code",
        data={"client_id": GOOGLE_CLIENT_ID, "scope": "https://www.googleapis.com/auth/drive.file"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Gagal minta device code: {resp.text[:200]}")
    r = resp.json()
    pending_save(r["device_code"], {
        "user_code": r["user_code"],
        "verification_url": r["verification_url"],
        "expires_at": time.time() + r["expires_in"],
        "interval": r.get("interval", 5),
    })
    return {
        "user_code": r["user_code"],
        "verification_url": r["verification_url"],
        "device_code": r["device_code"],
    }


@app.post("/api/auth/poll")
def api_poll_token(data: dict):
    device_code = (data or {}).get("device_code", "")
    if not device_code:
        return {"status": "error", "detail": "device_code wajib"}
    pending, sha = pending_load(device_code)
    if not pending:
        return {"status": "error", "detail": "Kode kadaluarsa atau tidak dikenal"}
    if time.time() > pending["expires_at"]:
        pending_del(device_code)
        return {"status": "error", "detail": "Kode sudah kedaluwarsa"}
    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    if resp.status_code == 200:
        token = resp.json()
        import secrets
        session_token = secrets.token_urlsafe(32)
        token["client_id"] = GOOGLE_CLIENT_ID
        token["client_secret"] = GOOGLE_CLIENT_SECRET
        save_token(session_token, token)
        try:
            creds = Credentials(
                token=token.get("access_token"), refresh_token=token.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            service = build("drive", "v3", credentials=creds)
            about = service.about().get(fields="user(emailAddress)").execute()
            email = about["user"]["emailAddress"]
        except Exception:
            email = ""
        st = state_get()
        st.setdefault("sessions", {})[session_token] = email
        state_save(st)
        pending_del(device_code)
        return {"status": "success", "session_token": session_token, "email": email}
    info = resp.json() if resp.text else {}
    err = info.get("error", "")
    if err in ("authorization_pending", "slow_down"):
        return {"status": "pending"}
    if err in ("expired_token", "invalid_grant"):
        pending_del(device_code)
        return {"status": "error", "detail": "Kode sudah kadaluarsa"}
    return {"status": "error", "detail": info.get("error_description", err)}


# ------------------------------------------------------------------ token API (worker)
@app.get("/api/token/{session_token}")
def api_token_get(session_token: str, req: Request):
    require_worker(req)
    token = load_token(session_token)
    if not token:
        raise HTTPException(status_code=404, detail="Token tidak ditemukan")
    return token


@app.post("/api/token/{session_token}")
def api_token_save(session_token: str, req: Request, body: dict):
    require_worker(req)
    token = load_token(session_token)
    if token:
        token.update(body or {})
    else:
        token = body or {}
    save_token(session_token, token)
    return {"ok": True}


# ------------------------------------------------------------------ Download task
class DownloadRequest(BaseModel):
    url: str
    filename: str = ""
    session_token: str = ""


@app.post("/api/download")
def process_download(req: DownloadRequest, request: Request):
    raw = req.url.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Input kosong")
    if raw.startswith("http://") or raw.startswith("https://"):
        raise HTTPException(status_code=400, detail="Masukkan kode pencarian, bukan URL!")

    st = state_get()
    st.setdefault("tasks", {})
    st.setdefault("history", [])
    st.setdefault("sessions", {})

    email = st.get("sessions", {}).get(req.session_token, "")

    # ---- duplicate by email
    dupe = next(
        (h for h in st.get("history", [])
         if h.get("email") == email and "".join(c for c in h.get("name", "") if c.isalnum()).lower() and (
            "".join(c for c in raw if c.isalnum()).lower() in
            "".join(c for c in h.get("name", "") if c.isalnum()).lower())),
        None,
    )
    if dupe:
        st["tasks"][raw] = {
            "id": raw, "status": "Selesai", "percent": 100, "speed": 0,
            "downloaded": 0, "total": 0, "clean_title": dupe.get("name", raw),
            "status_text": "Sudah ada di riwayat, unduhan dilewati.",
            "logs": [f"✅ [DUPLIKAT] '{dupe.get('name')}' sudah ada. Melewati unduhan."],
            "created": wib_time(), "updated": wib_time(),
        }
        state_save(st)
        return {"status": "started", "task_id": raw}

    if raw in st["tasks"] and st["tasks"][raw].get("status") in ("Memproses", "Mengunduh", "Mengunggah"):
        return {"status": "started", "task_id": raw}

    st["tasks"][raw] = {
        "id": raw, "status": "Scheduling", "percent": 0, "speed": 0,
        "downloaded": 0, "total": 0, "clean_title": "",
        "status_text": "Menunggu worker GitHub Actions...",
        "logs": ["🔍 Menerima input: {}".format(raw), "⏳ Menjadwalkan ke GitHub Actions..."],
        "created": wib_time(), "updated": wib_time(), "session_token": req.session_token,
    }
    state_save(st)

    try:
        dispatch_repo("jav-task", {"task_id": raw})
    except Exception as e:
        st = state_get()
        st.setdefault("tasks", {})
        if raw in st.get("tasks", {}):
            st["tasks"][raw]["status"] = "Gagal: scheduling"
            st["tasks"][raw]["status_text"] = f"Gagal dispatch GitHub Actions: {e}"
            st["tasks"][raw]["logs"].append(f"❌ {e}")
        state_save(st)
        raise HTTPException(status_code=500, detail=f"Gagal dispatch: {e}")
    return {"status": "started", "task_id": raw}


# ------------------------------------------------------------------ Task report (worker)
class ReportBody(BaseModel):
    task_id: str
    task: dict = {}
    history_item: dict | None = None


@app.post("/api/task/report")
def task_report(body: ReportBody, request: Request):
    require_worker(request)
    st = state_get()
    st.setdefault("tasks", {})
    st.setdefault("history", [])
    tid = body.task_id
    cur = st["tasks"].get(tid, {"id": tid})
    if isinstance(cur, dict):
        merged = {**cur}
        for k, v in (body.task or {}).items():
            if k == "logs" and isinstance(v, list):
                merged.setdefault("logs", []).extend(v)
                merged["logs"] = merged["logs"][-200:]
            else:
                merged[k] = v
        merged["updated"] = wib_time()
        st["tasks"][tid] = merged
    if body.history_item:
        item = body.history_item
        item["time"] = item.get("time") or wib_time()
        st["history"] = [h for h in st["history"] if h.get("name") != item.get("name")]
        st["history"].insert(0, item)
        st["history"] = st["history"][:200]
    state_save(st)
    return {"ok": True}


# ------------------------------------------------------------------ Progress
@app.get("/api/progress/{task_id:path}")
def get_progress(task_id: str):
    st = state_get()
    t = st.get("tasks", {}).get(task_id, {})
    return t


# ------------------------------------------------------------------ History
@app.get("/api/history")
def get_history(session_token: str = ""):
    if not session_token:
        return []
    st = state_get()
    email = st.get("sessions", {}).get(session_token, "")
    rows = st.get("history", [])
    out = [h for h in rows if (email and h.get("email") == email) or h.get("session_token") == session_token]
    return out[:50]


class DeleteRequest(BaseModel):
    filename: str
    delete_file: bool = False
    session_token: str = ""


def _thumb_gh_name(name):
    h = hashlib.sha256(name.encode()).hexdigest()[:16]
    return f"{h}.jpg"


@app.post("/api/history/delete")
def delete_history_item(req: DeleteRequest):
    st = state_get()
    st.setdefault("history", [])
    item = next((h for h in st["history"] if h.get("name") == req.filename), None)
    st["history"] = [h for h in st["history"] if h.get("name") != req.filename]
    state_save(st)
    if req.delete_file:
        if item and item.get("drive_file_id"):
            gdrive_delete_file(req.session_token, item["drive_file_id"])
        thumb = item.get("thumb") or _thumb_gh_name(req.filename)
        try:
            gh_delete(f"data/thumbs/{thumb}")
        except Exception:
            pass
    return {"status": "success"}


@app.delete("/api/history/clear")
def clear_history(session_token: str = ""):
    st = state_get()
    st.setdefault("history", [])
    if session_token:
        st["history"] = [h for h in st["history"] if h.get("session_token") != session_token]
    else:
        st["history"] = []
    state_save(st)
    return {"status": "cleared"}


# ------------------------------------------------------------------ Thumbnail
@app.get("/api/thumbnail/{name}")
def get_thumbnail(name: str):
    path = f"data/thumbs/{name}"
    b64, _ = gh_get(path)
    if not b64:
        # coba fallback "global" (tanpa nama)
        return StreamingResponse(iter([]), status_code=404, media_type="text/plain")
    data = base64.b64decode(b64)
    return StreamingResponse(iter([data]), media_type="image/jpeg")


# ------------------------------------------------------------------ UI
@app.get("/")
def serve_ui():
    html = get_full_ui(APP_VERSION, get_modals_html())
    return HTMLResponse(content=html)