# api/index.py
# FastAPI API/UI + GitHub Actions coordinator.
# Persistent tasks, sessions, history and automations live in PostgreSQL.
import base64
import hashlib
import json
import os
import re
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
from db import (init_db, create_task, update_task, patch_task_meta, add_log, get_task, upsert_session,
    get_session_email, upsert_history, list_history, delete_history, clear_history,
    find_history_duplicate, list_automations, upsert_automation, due_automations,
    mark_automation_run, db_check, search_automations, random_automations, autodb_status,
    delete_task, delete_tasks_by_session)
from ui.html import get_full_ui
from ui.modal import get_modals_html

app=FastAPI(title="Remote Uploader",docs_url=None,redoc_url=None)
DEV_MODE=bool(int((os.environ.get("DEV") or "0").strip() or "0"))
APP_VERSION="1.4.1 (Vercel + PostgreSQL + GitHub Actions + Playwright)"
if DEV_MODE:APP_VERSION+=" · DEV (suggestion hover aktif)"

GDRIVE_SCOPE="https://www.googleapis.com/auth/drive.file"
GH_TOKEN=os.environ.get("GH_TOKEN","");GH_REPO=os.environ.get("GH_REPO","");GH_BRANCH=os.environ.get("GH_BRANCH","main")
API_BASE=os.environ.get("API_BASE","").rstrip("/");WORKER_SECRET=os.environ.get("WORKER_SECRET","")
GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID","");GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET","")
_ENC=os.environ.get("API_ENC_KEY","").encode() or hashlib.sha256(((WORKER_SECRET or "puppeter")+"::enc").encode()).digest()
FERNET=Fernet(base64.urlsafe_b64encode(_ENC[:32]))

# Nama file workflow worker (harus cocok dengan path di repo)
WORKER_WORKFLOW_FILE="puppeter-worker.yml"

def _normalize_gdrive_folder(raw=None):
    """Normalisasi GDRIVE_FOLDER: hanya nama folder di root Drive.
    Buang prefix 'GDRIVE_FOLDER=' bila secret terlanjur terisi salah."""
    val=(raw or "").replace("GDRIVE_FOLDER=","").strip().strip("/")
    name=os.path.basename(val) if val else ""
    if not name or name in (".",".."):return "javColab"
    return name

GDRIVE_FOLDER=_normalize_gdrive_folder(os.environ.get("GDRIVE_FOLDER","javColab"))


def _db_ready():
    try:init_db();return True
    except Exception as e:raise HTTPException(status_code=503,detail=f"Database belum siap: {e}")

@app.on_event("startup")
def startup():
    # Jangan biarkan kegagalan koneksi/migrasi PostgreSQL mematikan
    # seluruh Vercel Function saat cold start. Endpoint akan mengembalikan
    # 503 yang jelas melalui _db_ready() bila database belum siap.
    if os.environ.get("DATABASE_URL"):
        try:
            init_db()
        except Exception as e:
            print(f"[startup] PostgreSQL belum siap: {e}", file=sys.stderr)

def _gh_headers(extra=None,auth=True):
    h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    if auth and GH_TOKEN:h["Authorization"]=f"Bearer {GH_TOKEN}"
    if extra:h.update(extra)
    return h

def gh_get(path):
    r=requests.get(f"https://api.github.com/repos/{GH_REPO}/contents/{path}",headers=_gh_headers(),timeout=20)
    if r.status_code==404:return None,None
    if r.status_code!=200:raise RuntimeError(f"GH get {path}: {r.status_code} {r.text[:200]}")
    d=r.json();return d.get("content"),d.get("sha")

def gh_put(path,content_b64,message="state update"):
    _,sha=gh_get(path);body={"message":message,"content":content_b64,"branch":GH_BRANCH}
    if sha:body["sha"]=sha
    r=requests.put(f"https://api.github.com/repos/{GH_REPO}/contents/{path}",headers=_gh_headers(),json=body,timeout=20)
    if r.status_code not in (200,201):raise RuntimeError(f"GH put {path}: {r.status_code} {r.text[:250]}")
    return r.json().get("content",{}).get("sha")

def gh_delete(path):
    _,sha=gh_get(path)
    if not sha:return True
    r=requests.delete(f"https://api.github.com/repos/{GH_REPO}/contents/{path}",headers=_gh_headers(),json={"message":f"delete {path}","sha":sha,"branch":GH_BRANCH},timeout=20)
    return r.status_code in (200,204)

def dispatch_repo(event_type,payload):
    """Trigger GitHub Actions worker.

    Prefer workflow_dispatch (eksplisit ke puppeter-worker.yml) karena lebih andal
    daripada repository_dispatch yang kadang tidak memunculkan run.
    Fallback ke repository_dispatch jika workflow_dispatch gagal.
    """
    if not GH_TOKEN:
        raise RuntimeError("GH_TOKEN kosong di environment Vercel — tidak bisa memicu GitHub Actions")
    if not GH_REPO:
        raise RuntimeError("GH_REPO kosong di environment Vercel — set contoh: nitrogen68/puppeter-web")

    task_id=str((payload or {}).get("task_id") or "").strip()
    errors=[]

    # 1) Primary: workflow_dispatch ke file workflow worker
    wd_url=f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{WORKER_WORKFLOW_FILE}/dispatches"
    wd_body={"ref":GH_BRANCH or "main","inputs":{"task_id":task_id}}
    try:
        r=requests.post(wd_url,headers=_gh_headers(),json=wd_body,timeout=20)
        if r.status_code in (200,201,204):
            return {"method":"workflow_dispatch","status":r.status_code}
        errors.append(f"workflow_dispatch HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        errors.append(f"workflow_dispatch exception: {e}")

    # 2) Fallback: repository_dispatch (event_type)
    rd_url=f"https://api.github.com/repos/{GH_REPO}/dispatches"
    rd_body={"event_type":event_type,"client_payload":payload or {}}
    try:
        r=requests.post(rd_url,headers=_gh_headers(),json=rd_body,timeout=20)
        if r.status_code in (200,201,204):
            return {"method":"repository_dispatch","status":r.status_code}
        errors.append(f"repository_dispatch HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        errors.append(f"repository_dispatch exception: {e}")

    raise RuntimeError(
        f"Gagal memicu worker (task_id={task_id!r}) repo={GH_REPO}. "
        + " | ".join(errors)
        + " — pastikan GH_TOKEN punya scope 'repo' + 'workflow', dan workflow file ada di branch main."
    )

def _gh_time(iso:str)->float:
    try:return datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()
    except Exception:return 0.0

def resolve_run_after_dispatch(method:str):
    """Cari run_id GitHub Actions yang baru dibuat oleh dispatch.
    workflow_dispatch/repository_dispatch tidak mengembalikan run_id,
    jadi kita ambil run terbaru dengan event+branch yang sama (< 90 detik)."""
    if not GH_REPO:return None
    try:
        if method=="workflow_dispatch":
            url=f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{WORKER_WORKFLOW_FILE}/runs"
        else:
            url=f"https://api.github.com/repos/{GH_REPO}/actions/runs"
        r=requests.get(url,headers=_gh_headers(),params={"branch":GH_BRANCH,"event":method,"per_page":5},timeout=15)
        if r.status_code!=200:return None
        for run in r.json().get("workflow_runs",[]):
            if _gh_time(run.get("created_at") or "") and time.time()-_gh_time(run.get("created_at") or "")>90:continue
            return {"run_id":run.get("id"),"run_number":run.get("run_number"),"html_url":run.get("html_url"),"status":run.get("status")}
    except Exception:return None
    return None

_iso_to_ms=lambda v: int(datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp()*1000) if v else 0

_STEP_CACHE={}
def _is_noise_gh_step(name):
    """Step yang tidak perlu ditampilkan ke user:
    'Post *' (post-job otomatis) & 'Upload worker diagnostics' (if: failure() —
    tidak pernah jalan → akan selalu ⏳ di UI)."""
    n=(name or "")
    return n.startswith("Post ") or n=="Upload worker diagnostics"

def gh_run_summary(run_id):
    """Status run + daftar step job worker real-time dari GitHub API (cache 1.5 dtk).

    Cache pendek agar step muncul SATU-PERSATU sesuai progres nyata job
    (Set up job → Checkout → ... → Run Puppeter), sinkron dengan polling UI ~2 dtk.
    Step noise (Post */upload diagnostics) di-filter supaya alur terbaca akurat."""
    key=str(run_id);now=time.time();c=_STEP_CACHE.get(key)
    if c and now-c[0]<1.5:return c[1]
    try:
        r=requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/runs/{run_id}/jobs",headers=_gh_headers(),params={"per_page":20},timeout=12)
        if r.status_code!=200:_STEP_CACHE[key]=(now,{});return {}
        jobs=r.json().get("jobs",[])
        if not jobs:_STEP_CACHE[key]=(now,{});return {}
        j=jobs[0]
        steps=[]
        for s in j.get("steps",[]):
            if _is_noise_gh_step(s.get("name","")):continue
            steps.append({"number":s.get("number"),"name":s.get("name"),"status":s.get("status"),"conclusion":s.get("conclusion")})
        summary={
            "status":j.get("status",""),
            "conclusion":j.get("conclusion") or "",
            "name":j.get("name",""),
            "steps":steps,
        }
        _STEP_CACHE[key]=(now,summary);return summary
    except Exception:return {}

def require_worker(req:Request):
    sec=(req.headers.get("x-worker-secret") or "").strip()
    bearer=(req.headers.get("authorization") or "").strip()
    gh_bearer=bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
    if WORKER_SECRET:
        if sec==WORKER_SECRET:
            return
        if GH_TOKEN and gh_bearer==GH_TOKEN:
            return
        raise HTTPException(status_code=401,detail="Worker authentication salah (WORKER_SECRET / GH_TOKEN tidak cocok)")
    return

def wib_time():return datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y %H:%M WIB")

def _normalize_code(raw:str)->str:
    s=(raw or "").strip()
    while s and s[-1] in ")]}\"'" and s.count("(") < s.count(")"):
        s=s[:-1].rstrip()
    while s and s[-1] in ")]}\"'" and s.count("[") < s.count("]"):
        s=s[:-1].rstrip()
    s=re.sub(r"\s+"," ",s).strip()
    return s

TOKEN_DIR="data/tokens";PENDING_DIR="data/pending"
def save_token(session_token,token_json):
    enc=FERNET.encrypt(json.dumps(token_json).encode());gh_put(f"{TOKEN_DIR}/{session_token}.enc",base64.b64encode(enc).decode(),"auto: token")
def load_token(session_token):
    b64,_=gh_get(f"{TOKEN_DIR}/{session_token}.enc")
    if not b64:return None
    try:return json.loads(FERNET.decrypt(base64.b64decode(b64)).decode())
    except InvalidToken:return None

def gdrive_service(session_token):
    token=load_token(session_token)
    if not token:raise HTTPException(status_code=404,detail="Sesi tidak terhubung")
    creds=Credentials(token=token.get("access_token"),refresh_token=token.get("refresh_token"),token_uri="https://oauth2.googleapis.com/token",client_id=token.get("client_id") or GOOGLE_CLIENT_ID,client_secret=token.get("client_secret") or GOOGLE_CLIENT_SECRET,scopes=[GDRIVE_SCOPE])
    if creds.expired:creds.refresh(GoogleRequest());token["access_token"]=creds.token;save_token(session_token,token)
    return build("drive","v3",credentials=creds)

def gdrive_delete_file(session_token,drive_file_id):
    try:
        if not drive_file_id:return False
        gdrive_service(session_token).files().delete(fileId=drive_file_id).execute();return True
    except Exception:return False

def pending_save(code,obj):gh_put(f"{PENDING_DIR}/{code}.json",base64.b64encode(json.dumps(obj).encode()).decode(),"auto: pending auth")
def pending_load(code):
    b64,sha=gh_get(f"{PENDING_DIR}/{code}.json");return (json.loads(base64.b64decode(b64).decode()),sha) if b64 else (None,None)
def pending_del(code):gh_delete(f"{PENDING_DIR}/{code}.json")

@app.post("/api/debug/dispatch")
def debug_dispatch(body:dict|None=None):
    """Uji trigger worker tanpa full download flow."""
    body=body or {}
    tid=str(body.get("task_id") or f"debug-{int(time.time())}").strip()
    try:
        info=dispatch_repo("jav-task",{"task_id":tid})
        return {"ok":True,"task_id":tid,"dispatch":info,"gh_repo":GH_REPO,"gh_token_set":bool(GH_TOKEN)}
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))

@app.get("/api/health")
def health():
    _db_ready()
    return {
        "ok":True,
        "app":APP_VERSION,
        "database":"postgresql",
        "worker":"github-actions",
        "playwright":"chromium",
        "gh_repo":bool(GH_REPO),
        "gh_token":bool(GH_TOKEN),
        "worker_secret":bool(WORKER_SECRET),
        "workflow":WORKER_WORKFLOW_FILE,
        "gdrive_folder":GDRIVE_FOLDER,
    }

@app.get("/api/db/check")
def api_db_check():
    """Cek endpoint khusus: pastikan semua database terload (Postgres + automation DB)."""
    _db_ready()
    tables,tok=db_check()
    autodbs,autook=autodb_status()
    ok=tok and autook
    return {"ok":ok,"status":"loaded" if ok else "missing","tables":tables,"databases":autodbs.get("databases",{}),"app":APP_VERSION}

@app.get("/api/automation/search")
def api_automation_search(q:str=""):
    """Cari kode dari automation DB (search_logs / javDbs.db).
    Dipakai UI untuk autocomplete — mis. ketik 'vem' → VEMA-101…VEMA-258."""
    _db_ready()
    q=(q or "").strip()
    return {"ok":True,"query":q,"results":search_automations(q)}

@app.get("/api/automation/random")
def api_automation_random(n:int=15):
    """Kode video_id acak dari pool database — dipakai suggestion on hover (dev).
    Jumlah di-random oleh UI (10–20); endpoint membatasi maks 50."""
    _db_ready()
    n=max(1,min(50,int(n or 15)))
    return {"ok":True,"results":random_automations(n)}

@app.get("/api/auth/status")
def api_auth_status(session_token:str=""):
    if not session_token:return {"connected":False}
    _db_ready();email=get_session_email(session_token)
    if email:return {"connected":True,"email":email}
    token=load_token(session_token)
    if not token:return {"connected":False}
    try:
        about=build("drive","v3",credentials=gdrive_service(session_token)).about().get(fields="user(emailAddress)").execute();email=about["user"]["emailAddress"];upsert_session(session_token,email);return {"connected":True,"email":email}
    except Exception as e:return {"connected":False,"error":str(e)}

@app.post("/api/auth/device")
def api_start_device_flow():
    if not GOOGLE_CLIENT_ID:raise HTTPException(status_code=500,detail="GOOGLE_CLIENT_ID belum di-set")
    r=requests.post("https://oauth2.googleapis.com/device/code",data={"client_id":GOOGLE_CLIENT_ID,"scope":"https://www.googleapis.com/auth/drive.file"},timeout=15)
    if r.status_code!=200:raise HTTPException(status_code=500,detail=f"Gagal minta device code: {r.text[:200]}")
    x=r.json();pending_save(x["device_code"],{"user_code":x["user_code"],"verification_url":x["verification_url"],"expires_at":time.time()+x["expires_in"],"interval":x.get("interval",5)});return {"user_code":x["user_code"],"verification_url":x["verification_url"],"device_code":x["device_code"]}

@app.post("/api/auth/poll")
def api_poll_token(data:dict):
    code=(data or {}).get("device_code","")
    if not code:return {"status":"error","detail":"device_code wajib"}
    pending,_=pending_load(code)
    if not pending:return {"status":"error","detail":"Kode kadaluarsa atau tidak dikenal"}
    if time.time()>pending["expires_at"]:pending_del(code);return {"status":"error","detail":"Kode sudah kedaluwarsa"}
    try:r=requests.post("https://oauth2.googleapis.com/token",data={"client_id":GOOGLE_CLIENT_ID,"client_secret":GOOGLE_CLIENT_SECRET,"device_code":code,"grant_type":"urn:ietf:params:oauth:grant-type:device_code"},timeout=15)
    except Exception as e:return {"status":"error","detail":str(e)}
    if r.status_code==200:
        token=r.json();import secrets
        session=secrets.token_urlsafe(32);token["client_id"]=GOOGLE_CLIENT_ID;token["client_secret"]=GOOGLE_CLIENT_SECRET;save_token(session,token);email=""
        try:
            creds=Credentials(token=token.get("access_token"),refresh_token=token.get("refresh_token"),token_uri="https://oauth2.googleapis.com/token",client_id=GOOGLE_CLIENT_ID,client_secret=GOOGLE_CLIENT_SECRET,scopes=[GDRIVE_SCOPE]);email=build("drive","v3",credentials=creds).about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
        except Exception:pass
        _db_ready();upsert_session(session,email);pending_del(code);return {"status":"success","session_token":session,"email":email}
    info=r.json() if r.text else {};err=info.get("error","")
    if err in ("authorization_pending","slow_down"):return {"status":"pending"}
    if err in ("expired_token","invalid_grant"):pending_del(code);return {"status":"error","detail":"Kode sudah kedaluwarsa"}
    return {"status":"error","detail":info.get("error_description",err)}

@app.get("/api/token/{session_token}")
def api_token_get(session_token:str,req:Request):
    require_worker(req);token=load_token(session_token)
    if not token:raise HTTPException(status_code=404,detail="Token tidak ditemukan")
    return token

@app.post("/api/token/{session_token}")
def api_token_save(session_token:str,req:Request,body:dict):
    require_worker(req);token=load_token(session_token) or {};token.update(body or {});save_token(session_token,token);return {"ok":True}

class DownloadRequest(BaseModel):
    url:str;filename:str="";session_token:str="";test:bool=False

def _launch_task(raw:str,session_token:str="",test:bool=False):
    """Buat task lalu dispatch ke GitHub Actions. Dipakai jalur NORMAL dan jalur TEST.

    - test=True → tidak butuh login, selalu mulai bersih (hapus task lama), tanpa lock
      429 & tanpa cek history, cocok untuk verifikasi logika UI/backend berulang.
    - Normal → proteksi duplikat (lock 120 dtk + cek history) + log bersih.
    """
    _db_ready()
    if test:
        # Uji: mulai murni dari 0% — hapus task lama (log + preview) biar tidak numpuk.
        if get_task(raw):delete_task(raw)
    else:
        email=get_session_email(session_token) if session_token else ""
        existing=get_task(raw)
        active_statuses=("Memproses","Mengunduh","Mengunggah","Memproses pencarian...")
        if existing and existing.get("status") in active_statuses:
            return {"status":"started","task_id":raw,"skipped":"already_running","current_status":existing.get("status")}
        if existing:
            created=existing.get("created_at")
            if created:
                try:
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(str(created).replace("Z","+00:00"))).total_seconds()
                    if age<120:
                        raise HTTPException(status_code=429,detail=f"Kode {raw} baru saja diproses ({max(0,int(age))}s lalu) — token anti-duplikat: coba lagi dalam {max(1,int(120-age))} detik.")
                except ValueError:
                    pass
            delete_task(raw)
        dupe=find_history_duplicate(raw,email) if email else None
        if dupe:
            create_task(raw,raw,session_token,{"clean_title":dupe.get("name",raw),"status_text":"Sudah ada di riwayat, unduhan dilewati."});update_task(raw,status="Selesai",progress=100,message="Sudah ada di riwayat",completed_at=datetime.now(timezone.utc));add_log(raw,f"✅ [DUPLIKAT] '{dupe.get('name',raw)}' sudah ada. Melewati unduhan.");return {"status":"started","task_id":raw,"skipped":"duplicate"}
    meta={"clean_title":"","status_text":"Menunggu worker GitHub Actions...","created":wib_time(),"mode":"preview","confirmed":False}
    if test:meta["test"]=True
    create_task(raw,raw,session_token,meta)
    if test:
        add_log(raw,"🧪 [TEST] Menjadwalkan simulasi UI/backend ke GitHub Actions (tanpa login)...")
    else:
        add_log(raw,"⏳ Menjadwalkan ke GitHub Actions (mode PREVIEW)...")
    update_task(raw,status="Scheduling",message="Memicu GitHub Actions..."+(" (TEST)" if test else ""),session_token=session_token)
    try:
        info=dispatch_repo("jav-task",{"task_id":raw})
        add_log(raw,f"✅ Dispatch berhasil via {info.get('method')} HTTP {info.get('status')} — cek tab Actions (Puppeter Worker)")
        run=resolve_run_after_dispatch(info.get("method") or "") or None
        if run:
            patch_task_meta(raw,{"github":run})
            add_log(raw,f"▶️ GitHub Action: run #{run.get('run_number') or run.get('run_id')} — {run.get('html_url')}")
        update_task(raw,status="queued",message=f"Menunggu runner ({info.get('method')})...")
    except Exception as e:
        update_task(raw,status="Gagal: scheduling",message=f"Gagal dispatch GitHub Actions: {e}",error=str(e));add_log(raw,f"❌ {e}","error");raise HTTPException(status_code=500,detail=f"Gagal dispatch: {e}")
    return {"status":"started","task_id":raw,"dispatch":info}

@app.post("/api/download")
def process_download(req:DownloadRequest):
    raw=_normalize_code(req.url)
    if not raw:raise HTTPException(status_code=400,detail="Input kosong")
    if raw.startswith(("http://","https://")):raise HTTPException(status_code=400,detail="Masukkan kode pencarian, bukan URL!")
    test=bool(req.test) or raw.upper().startswith("TEST")
    if not req.session_token and not test:
        raise HTTPException(status_code=401,detail="Harus login Google Drive dulu sebelum unduh")
    return _launch_task(raw,req.session_token or "",test)

# ===== ENDPOINT KHUSUS TESTING UI & BACKEND (tanpa login) =====

@app.get("/api/test/status")
def api_test_status():
    """Status lingkungan uji — dipakai UI Mode Tes tau test harness eksternal."""
    return {"ok":True,"mode":"test","login_required":False,
            "message":"Mode Tes aktif — jalankan simulasi dispatch+worker untuk memverifikasi logika UI/backend."}

class TestRunRequest(BaseModel):
    code:str="TEST-001"

@app.post("/api/test/run")
def api_test_run(body:TestRunRequest):
    """Endpooint khusus testing UI & backend TANPA login sama sekali.

    Membuat task bertanda TEST lalu dispatch ke worker GitHub Actions (NYATA).
    Worker menjalankan simulasi penuh: log real-time, step GitHub, bar progres,
    preview, konfirmasi, hingga Selesai — semua tampil di UI seperti produksi.
    Gunakan /api/reset untuk membersihkan state hasil pengujian."""
    _db_ready()
    raw=_normalize_code(body.code or "TEST-001")
    return _launch_task(raw,"",True)

class TestResetRequest(BaseModel):
    task_id:str=""

@app.post("/api/test/reset")
def api_test_reset(body:TestResetRequest):
    """Reset khusus uji — membersihkan task TEST di server (log+preview+result).
    Tidak memerlukan login; setara /api/reset untuk task bertanda TEST."""
    _db_ready();tid=(body.task_id or "").strip()
    if tid:
        t=get_task(tid)
        ok=bool(t) and bool((t.get("meta") or {}).get("test")) if t else False
        if not ok and tid.upper().startswith("TEST"):ok=True
        if ok:
            delete_task(tid);return {"ok":True,"cleared":tid}
        if t:raise HTTPException(status_code=403,detail="Hanya task TEST yang boleh di-reset lewat endpoint ini; gunakan /api/reset untuk task biasa.")
    return {"ok":True,"cleared":None}

class ConfirmRequest(BaseModel):
    task_id:str;session_token:str=""

class ResetRequest(BaseModel):
    task_id:str="";session_token:str=""

@app.post("/api/reset")
def hard_reset(req:ResetRequest):
    """Hard reset (dipanggil oleh tombol Reset di UI setelah konfirmasi).

    Hanya menghapus state di database (task + seluruh log/result preview lama).
    TIDAK memicu /dispatch atau proses scraping apa pun — worker tidak disentuh.
    Frontend wajib membersihkan state lokal (localStorage/sessionStorage) sendiri.
    """
    _db_ready()
    tid=(req.task_id or "").strip()
    if tid:
        delete_task(tid)
        return {"ok":True,"cleared":"task","task_id":tid}
    if req.session_token:
        n=delete_tasks_by_session(req.session_token)
        return {"ok":True,"cleared":"session","session_token":req.session_token,"cleared_count":n}
    return {"ok":True,"cleared":None}

@app.post("/api/download/confirm")
def confirm_download(req:ConfirmRequest):
    """Konfirmasi preview → worker yang SAMA (sedang menunggu) melanjutkan unduh
    penuh tanpa dispatch/re-run baru. Progres berlanjut, tidak di-reset."""
    tid=req.task_id.strip()
    if not tid:raise HTTPException(status_code=400,detail="task_id wajib")
    if not req.session_token:raise HTTPException(status_code=401,detail="Harus login Google Drive dulu")
    _db_ready();current=get_task(tid)
    if not current:raise HTTPException(status_code=404,detail=f"Task {tid} tidak ditemukan")
    if current.get("confirmed"):
        return {"status":"already_confirmed","task_id":tid,"current_status":current.get("status")}
    meta=dict(current.get("meta") or {});meta["confirmed"]=True;meta["mode"]="download"
    update_task(tid,meta=meta,session_token=req.session_token,status="Memproses unduhan...",message="Konfirmasi diterima — mendownload penuh...",progress=20)
    add_log(tid,"✅ Konfirmasi diterima — worker melanjutkan unduh penuh tanpa restart.")
    return {"status":"confirmed","task_id":tid,"confirmed":True}

class ReportBody(BaseModel):
    task_id:str;task:dict={};history_item:dict|None=None

@app.post("/api/task/report")
def task_report(body:ReportBody,request:Request):
    require_worker(request);_db_ready();tid=body.task_id;current=get_task(tid)
    if not current:create_task(tid,tid,"");current=get_task(tid)
    fields=dict(body.task);logs=fields.pop("logs",[]) if isinstance(fields.get("logs"),list) else []
    meta=current.get("meta") or {};meta.update({k:v for k,v in fields.items() if k not in {"status","percent","speed","downloaded","total","clean_title","status_text","session_token"}})
    mapping={"status":"status","percent":"progress","speed":"speed_kbps","size":"size_bytes","status_text":"message"};core={}
    for src,dst in mapping.items():
        if src in fields:core[dst]=fields[src]
    for key in ("downloaded","total","clean_title"):
        if key in fields:meta[key]=fields[key]
    if "session_token" in fields:core["session_token"]=fields["session_token"]
    if "status" in fields and str(fields["status"]).lower() in {"selesai","completed","success","gagal","failed"}:core["completed_at"]=datetime.now(timezone.utc)
    core["meta"]=meta;update_task(tid,**core)
    for line in logs:add_log(tid,str(line))
    if body.history_item and body.history_item.get("name"):
        item=dict(body.history_item);item.setdefault("time",wib_time())
        if not item.get("email") and current.get("session_token"):item["email"]=get_session_email(current["session_token"])
        upsert_history(item)
    return {"ok":True}

@app.get("/api/progress/{task_id:path}")
def get_progress(task_id:str):
    _db_ready();t=get_task(task_id)
    if not t:return {}
    meta=t.pop("meta",{}) or {};code=t.get("code") or task_id
    out={"id":code,"task_id":t.get("task_id"),"status":t.get("status"),"percent":t.get("progress",0),"speed":t.get("speed_kbps",0),"downloaded":meta.get("downloaded",0),"total":meta.get("total",t.get("size_bytes",0)),"clean_title":meta.get("clean_title",""),"status_text":t.get("message",meta.get("status_text","")),"logs":[{"id":x.get("id"),"ts":_iso_to_ms(x.get("created_at")),"level":x.get("level","info"),"message":x.get("message","")} for x in t.get("logs",[])],"created":meta.get("created",t.get("created_at")),"updated":t.get("updated_at"),"session_token":t.get("session_token","")}
    out["preview"]=meta.get("preview") or None
    out["confirmed"]=bool(meta.get("confirmed"))
    out["mode"]=str(meta.get("mode") or ("download" if out["confirmed"] else "preview"))
    out["test"]=bool(meta.get("test"))
    github=dict(meta.get("github") or {})
    # LAZY RUN RESOLUTION: right setelah workflow_dispatch HTTP 204, GitHub belum
    # mencatat run-nya sehingga resolve di _launch_task sering gagal. Di sini run
    # dicari ulang pada SETIAP poll (≈ sekali memanggil API GitHub) sampai ketemu —
    # begitu ketemu, baris run + step muncul real-time, tanpa jeda diam di UI.
    if not github.get("run_id"):
        st=(t.get("status") or "")
        if st not in ("Selesai","preview_ready","Gagal","Gagal: scheduling","Gagal unduhan"):
            r=resolve_run_after_dispatch("workflow_dispatch")
            if r:
                github=r
                try:patch_task_meta(t.get("task_id") or task_id,{"github":r})
                except Exception:pass
    out["github"]=github
    if github.get("run_id"):
        try:out["run"]=gh_run_summary(github["run_id"])
        except Exception:out["run"]={}
    if t.get("result") is not None:out["result"]=t["result"]
    if t.get("error"):out["error"]=t["error"]
    return out

@app.get("/api/history")
def get_history(session_token:str=""):
    _db_ready();email=get_session_email(session_token) if session_token else "";return list_history(session_token=session_token,email=email,limit=50) if session_token else []

class DeleteRequest(BaseModel):
    filename:str;delete_file:bool=False;session_token:str=""

def _thumb_gh_name(name):return f"{hashlib.sha256(name.encode()).hexdigest()[:16]}.jpg"

@app.post("/api/history/delete")
def delete_history_item(req:DeleteRequest):
    _db_ready();rows=list_history(session_token=req.session_token,limit=200);item=next((h for h in rows if h.get("name")==req.filename),None);delete_history(req.filename,req.session_token)
    if req.delete_file:
        if item and item.get("drive_file_id"):gdrive_delete_file(req.session_token,item["drive_file_id"])
        try:gh_delete(f"data/thumbs/{item.get('thumb') or _thumb_gh_name(req.filename)}")
        except Exception:pass
    return {"status":"success"}

@app.delete("/api/history/clear")
def clear_history_api(session_token:str=""):
    _db_ready();clear_history(session_token);return {"status":"cleared"}

@app.get("/api/thumbnail/{name}")
def get_thumbnail(name:str):
    b64,_=gh_get(f"data/thumbs/{name}")
    if not b64:return StreamingResponse(iter([]),status_code=404,media_type="text/plain")
    return StreamingResponse(iter([base64.b64decode(b64)]),media_type="image/jpeg")

class AutomationBody(BaseModel):
    name:str;interval_minutes:int=60;action:str="worker";config:dict={};enabled:bool=True

@app.get("/api/automation")
def automation_list(request:Request):
    require_worker(request);_db_ready();return list_automations()

@app.post("/api/automation")
def automation_save(body:AutomationBody,request:Request):
    require_worker(request);_db_ready();return {"ok":True,"id":upsert_automation(body.name,body.interval_minutes,body.action,body.config,body.enabled)}

@app.post("/api/automation/run")
def automation_run(request:Request):
    require_worker(request);_db_ready();results=[]
    for a in due_automations():
        cfg=a.get("config") or {};code=str(cfg.get("code") or cfg.get("url") or "").strip()
        if not code:mark_automation_run(a["id"]);results.append({"id":a["id"],"status":"skipped","reason":"config.code kosong"});continue
        tid=f"auto-{a['id']}-{int(time.time())}";create_task(tid,code,str(cfg.get("session_token") or ""),{"automation_id":a["id"],"created":wib_time()});add_log(tid,f"🤖 Automation '{a['name']}' dijalankan")
        try:dispatch_repo("jav-task",{"task_id":tid});mark_automation_run(a["id"])
        except Exception as e:update_task(tid,status="Gagal: scheduling",error=str(e),message=str(e));results.append({"id":a["id"],"status":"error","error":str(e)});continue
        if GH_REPO:
            try:
                run=resolve_run_after_dispatch("workflow_dispatch")
                if run:
                    patch_task_meta(tid,{"github":run});add_log(tid,f"▶️ GitHub Action: run #{run.get('run_number') or run.get('run_id')} — {run.get('html_url')}")
            except Exception:pass
        results.append({"id":a["id"],"task_id":tid,"status":"dispatched"})
    return {"ok":True,"results":results}

@app.get("/api",response_class=HTMLResponse,include_in_schema=False)
@app.get("/api/",response_class=HTMLResponse,include_in_schema=False)
def serve_api_ui():return HTMLResponse(content=get_full_ui(APP_VERSION,get_modals_html(),DEV_MODE))

@app.get("/",response_class=HTMLResponse,include_in_schema=False)
def serve_ui():return HTMLResponse(content=get_full_ui(APP_VERSION,get_modals_html(),DEV_MODE))
