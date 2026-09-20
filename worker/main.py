#!/usr/bin/env python3
# worker/main.py — pelaksana tugas berat di GitHub Actions.
# Mendapatkan task_id, membaca state via API Vercel, scraping+download+upload GDrive,
# lalu melaporkan progres & hasil kembali ke state (Vercel/GitHub).
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib3
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE = os.environ.get("API_BASE", "").rstrip("/")
WORKER_SECRET = os.environ.get("WORKER_SECRET", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
MIN_FILESIZE = 5 * 1024 * 1024
# Scope Google Drive harus konsisten dengan Google Cloud Console (drive.file).
# Scope yang tidak konsisten menyebabkan invalid_scope saat refresh token.
GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
# Setelah preview siap, worker MENUNGGU konfirmasi user (tanpa re-run/dispatch baru).
WAIT_CONFIRM_TIMEOUT = int(os.environ.get("WAIT_CONFIRM_TIMEOUT", "900"))
CONFIRM_POLL_INTERVAL = 5
# Byse (via API) — key diambil dari GitHub Actions secret BYSE_API_KEY.
BYSE_API_BASE = os.environ.get("BYSE_API_BASE", "https://api.byse.sx").rstrip("/")
BYSE_API_KEY = os.environ.get("BYSE_API_KEY", "").strip()


def _normalize_gdrive_folder(raw=None):
    """Normalisasi GDRIVE_FOLDER: hanya nama folder di root Drive.
    Buang prefix 'GDRIVE_FOLDER=' bila secret terlanjur terisi salah,
    ambil basename, fallback 'javColab' jika kosong/'.'/..'."""
    val = (raw or "").replace("GDRIVE_FOLDER=", "").strip().strip("/")
    name = os.path.basename(val) if val else ""
    if not name or name in (".", ".."):
        return "javColab"
    return name


GDRIVE_FOLDER = _normalize_gdrive_folder(os.environ.get("GDRIVE_FOLDER", "javColab"))

task_id = ""
_last_report = 0.0
_report_queue = []  # logs buffer


def wib():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y %H:%M WIB")


def log(msg):
    print(msg, flush=True)
    _report_queue.append(str(msg))


def github_context():
    """Konteks run GitHub Actions agar terlihat real-time di terminal log UI."""
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id:
        return {}
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    return {
        "run_id": run_id,
        "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        "step": os.environ.get("GITHUB_ACTION", ""),
        "html_url": f"https://github.com/{repo}/actions/runs/{run_id}" if repo else "",
    }


def report(task_fields=None, history_item=None, force=False):
    global _last_report
    now = time.time()
    if not force and now - _last_report < 2.0 and not _report_queue:
        return
    body = {"task_id": task_id, "task": {}}
    if _report_queue:
        body["task"]["logs"] = _report_queue[:100]
        _report_queue.clear()
    if task_fields:
        body["task"].update(task_fields)
    ctx = github_context()
    if ctx:
        body["task"]["github"] = ctx
    if history_item:
        body["history_item"] = history_item

    headers = {"Content-Type": "application/json"}
    if WORKER_SECRET:
        headers["X-Worker-Secret"] = WORKER_SECRET
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"

    try:
        r = requests.post(
            f"{API_BASE}/api/task/report",
            json=body,
            headers=headers,
            timeout=20,
        )
        print(f"[diag] API report HTTP {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"[report] WARN HTTP {r.status_code}: {r.text[:200]}", flush=True)
            return  # soft-fail: jangan kill worker
        _last_report = now
    except Exception as e:
        print(f"[report] WARN (soft-fail): {e}", flush=True)
        return  # soft-fail
def get_task():
    st = requests.get(f"{API_BASE}/api/progress/{requests.utils.quote(task_id, safe='')}",
                      timeout=20).json()
    return st


def _worker_headers():
    headers = {"Content-Type": "application/json"}
    if WORKER_SECRET:
        headers["X-Worker-Secret"] = WORKER_SECRET
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    return headers


def byse_local_upload(file_path, title=""):
    """Upload file lokal ke akun Byse via API (multipart ke upload/server).
    Tahap 1: upload/server → dapatkan URL upload dinamis (result).
    Tahap 2: POST multipart field 'key' + 'file' → balasan "files":[{"filecode"...}].
    Ambil filecode dengan parsing yang toleran; fallback cari via folder/list."""
    if not BYSE_API_KEY:
        raise RuntimeError("BYSE_API_KEY belum diset (GitHub Actions secret)")
    _ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        j = requests.get(f"{BYSE_API_BASE}/upload/server", params={"key": BYSE_API_KEY, "fld_id": "0"}, headers=_ua, timeout=30).json()
    except Exception as e:
        raise RuntimeError(f"Byse upload/server gagal: {e}")
    srv = j.get("result") or ""
    if not (isinstance(srv, str) and srv.startswith("http")):
        raise RuntimeError(f"Byse upload/server gagal: {j.get('msg') or j}")
    srv_url = srv.rstrip("/")
    log(f"⬆️ Byse: upload lokal ke {srv_url.split('/')[2]} ...")
    with open(file_path, "rb") as f:
        r = requests.post(
            srv_url,
            data={"key": BYSE_API_KEY},
            files=[("file", (os.path.basename(file_path), f, "application/octet-stream"))],
            headers=_ua,
            timeout=1800,
        )
    try:
        jr = r.json()
    except Exception:
        raise RuntimeError(f"Respon upload Byse tidak valid: {r.text[:200]}")

    def _take_fc(obj):
        import json as _json
        if isinstance(obj, dict):
            for k in ("files", "result", "data", "rows"):
                v = obj.get(k)
                if (isinstance(v, list) or isinstance(v, dict)) and _take_fc(v):
                    return _take_fc(v)
            return str(obj.get("filecode") or obj.get("file_code") or obj.get("id") or "")
        if isinstance(obj, list) and obj:
            return _take_fc(obj[0])
        if isinstance(obj, str):
            s = obj.strip()
            try:
                inner = _json.loads(s)
                if isinstance(inner, dict):
                    return _take_fc(inner)
            except Exception:
                pass
            # "UPLOAD SUCCESS" / pesan lain bukan filecode → jangan diterima
            return s if len(s) == 12 and s.isalnum() else ""
        return ""

    fc = _take_fc(jr if isinstance(jr, dict) else jr)
    if not fc:
        log("⚠️ Respons upload tidak memuat filecode — mencoba mencarinya via folder/list...")
        try:
            res = requests.get(f"{BYSE_API_BASE}/folder/list",
                               params={"key": BYSE_API_KEY, "fld_id": "0", "files": "1"}, headers=_ua, timeout=30).json()
            # file terbaru yang baru di-upload → kandidat paling akhir di daftar
            rows = res.get("files") if isinstance(res, dict) else (res if isinstance(res, list) else [])
            rows = rows if isinstance(rows, list) else []
            for row in reversed(list(rows)):
                rid = row.get("file_code") or row.get("filecode") or row.get("id") or ""
                if isinstance(row, dict) and rid:
                    fc = str(rid)
                    break
        except Exception:
            fc = ""
    if not fc:
        raise RuntimeError(f"Byse upload gagal: {r.text[:300]}")
    log(f"✅ File ter-upload ke Byse (filecode {fc}).")
    return str(fc)


def byse_file_info(file_code):
    """Info file Byse via file/info: mengembalikan dict (mis. download_url, size)."""
    _ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    j = requests.get(f"{BYSE_API_BASE}/file/info", params={"key": BYSE_API_KEY, "file_code": file_code}, headers=_ua, timeout=30).json()
    res = j.get("result") if isinstance(j, dict) else j
    rows = res if isinstance(res, list) else ([res] if res else [])
    return rows[0] if rows else (res if isinstance(res, dict) else {})


def byse_link(file_code, info=None):
    """URL file di Byse: prefer field link dari file/info, fallback https://byse.sx/d/CODE."""
    d = info or {}
    for k in ("download_url", "download_link", "link", "protected_dl", "download"):
        v = d.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return f"https://byse.sx/d/{file_code}"


def byse_remote_add(url, title=""):
    """remote/add: Byse menarik URL CDN. Mengembalikan (filecode, msg, raw)."""
    if not BYSE_API_KEY:
        raise RuntimeError("BYSE_API_KEY belum diset (GitHub Actions secret)")
    _ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(f"{BYSE_API_BASE}/remote/add",
                     params={"key": BYSE_API_KEY, "url": url, "fld_id": "0", "file_title": (title or "")[:200]},
                     headers=_ua, timeout=30)
    raw = r.json()
    res = raw.get("result") if isinstance(raw, dict) else raw
    fc = ""
    if isinstance(res, dict):
        for k in ("files", "result", "data"):
            v = res.get(k)
            if not fc and (isinstance(v, list) or isinstance(v, dict)):
                fc = _fc_from(v)
        if not fc:
            fc = str(res.get("filecode") or res.get("file_code") or "")
    elif isinstance(res, list):
        fc = _fc_from(res)
    if not fc and isinstance(raw, dict):
        fc = str(raw.get("filecode") or raw.get("file_code") or "")
    return fc, str(raw.get("msg") or ""), raw


def _fc_from(obj):
    if isinstance(obj, dict):
        return str(obj.get("filecode") or obj.get("file_code") or obj.get("id") or "")
    if isinstance(obj, list) and obj:
        return _fc_from(obj[0])
    return ""


def byse_remote_status(file_code):
    """remote/status: status penarikan. Mengembalikan baris dict yang cocok."""
    _ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    raw = requests.get(f"{BYSE_API_BASE}/remote/status",
                       params={"key": BYSE_API_KEY, "file_code": file_code}, headers=_ua, timeout=30).json()
    res = raw.get("result") if isinstance(raw, dict) else raw
    rows = res if isinstance(res, list) else ([res] if res else [])
    for row in rows:
        if isinstance(row, dict) and str(row.get("file_code") or row.get("filecode") or row.get("id") or "") == str(file_code):
            return row
    if isinstance(res, dict):
        return res
    return rows[0] if rows else {}


def byse_search_files(title):
    """Cari file di akun Byse berdasarkan judul (kasus remote sudah ada/gagal)."""
    q = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    if not q:
        return {}
    _ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    raw = requests.get(f"{BYSE_API_BASE}/folder/list",
                       params={"key": BYSE_API_KEY, "fld_id": "0", "files": "1"}, headers=_ua, timeout=30).json()
    rows = raw.get("files") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    rows = rows if isinstance(rows, list) else []
    words = [w for w in q.split() if len(w) >= 4]
    best = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ft = re.sub(r"[^a-z0-9]+", " ", str(row.get("name") or row.get("title") or "")).lower()
        if words and all(w in ft for w in words[:2]):
            return row
        if q[:10] and (q[:10] in ft or ft[:10] in q):
            best = row or best
    return best


def _byse_finalize(file_code, title, session_token, fname, size_from=""):
    """Rekam hasil sukses Byse: ambil info (download_url) → report Selesai + riwayat."""
    try:
        info = byse_file_info(file_code)
    except Exception:
        info = {}
    url = byse_link(file_code, info)
    size = size_from or str(info.get("size") or "")
    hist = {
        "session_token": session_token,
        "email": "",
        "name": fname,
        "size": size,
        "time": wib(),
        "status": "success",
        "path": "",
        "drive_file_id": "",
        "byse_url": url,
        "thumb": "",
    }
    report({"status": "Selesai", "percent": 100, "downloaded": 0, "total": 0, "speed": 0,
            "clean_title": title, "status_text": "Berhasil disimpan ke Byse (via API).",
            "byse_url": url, "byse_filecode": file_code}, hist, force=True)
    log(f"🎬 Selesai! File tersedia di Byse: {url}")


def run_byse_destination(cdn, page_url, title, session_token):
    """Tujuan 'byse': kirim URL CDN ke Byse via API remote/add; jika pull remote
    gagal/lewat waktu → fallback upload lokal dari runner (garansi tombol selalu berfungsi)."""
    fname = clean_filename(title, page_url)
    # Segarkan CDN dulu (token baru). CDN playmogo/fast-stream diberi token+kedaluwarsa
    # pendek — token lama membuat remote pull "putus di tengah" (kasus user barusan).
    try:
        fresh, _ft, _fp = asyncio.new_event_loop().run_until_complete(sniper_extract_cdn(page_url))
        if fresh:
            cdn = fresh
            log("🔄 CDN di-refresh (token baru) agar remote/unduh tidak putus di tengah.")
    except Exception as e:
        log(f"[byse] refresh CDN skip: {str(e)[:120]}")
    log("🎬 Tujuan 'byse': mengirim URL CDN ke Byse via API (remote/add)...")
    try:
        fc, msg, raw = byse_remote_add(cdn, title)
        log(f"[byse] respon remote/add -> {json.dumps(raw)[:400] or msg[:400]}")
    except Exception as e:
        fc = ""
        log(f"[byse] remote/add error: {str(e)[:200]}")
    if fc:
        log(f"🎬 Byse menerima URL CDN (filecode {fc}). Menunggu remote pull selesai...")
        deadline = time.time() + 2400  # 40 menit maks
        while time.time() < deadline:
            st = byse_remote_status(fc)
            raw_s = str(st.get("status") or "").lower()
            bd = int(st.get("bytes_downloaded") or 0)
            bt = int(st.get("bytes_total") or 0)
            done = raw_s in ("completed", "complete", "done", "success", "10", "100") or (bt > 0 and bd >= bt)
            if done:
                _byse_finalize(fc, title, session_token, fname)
                return
            if raw_s in ("error", "failure", "failed", "canceled", "cancelled"):
                log(f"[byse] remote pull status error: {json.dumps(st)[:200]}")
                break
            if bt > 0:
                pct = 10 + (85 * bd // bt)
                pct = min(pct, 99)
                report({"status": "Mengunggah ke Byse (via API)...", "percent": pct, "clean_title": title,
                        "status_text": f"Byse menarik CDN: {bd // 1024 // 1024} MB / {bt // 1024 // 1024} MB"}, force=True)
                log(f"Byse menarik CDN: {bd // 1024 // 1024} / {bt // 1024 // 1024} MB")
            time.sleep(8)
        log("⚠️ Remote pull gagal/lewat batas waktu → fallback upload lokal dari runner.")
    else:
        existing = byse_search_files(title)
        ex_code = (existing or {}).get("file_code") or (existing or {}).get("filecode") or (existing or {}).get("id") or ""
        if existing and ex_code:
            log("🎬 File sudah ada di akun Byse — memakai link yang sudah tersedia.")
            _byse_finalize(str(ex_code), title, session_token, fname, size_from=str((existing or {}).get("size") or ""))
            return
        log("⚠️ Remote upload tidak menghasilkan filecode → fallback upload lokal dari runner.")
    run_byse_upload(cdn, page_url, title, session_token, start_pct=15)


def run_byse_upload(cdn, page_url, title, session_token, start_pct=20):
    """Tujuan 'byse': unduh penuh lalu upload lokal ke Byse (via API)."""
    log("🎬 Tujuan 'byse': mengunduh penuh lalu upload lokal ke Byse via API...")
    fname = clean_filename(title, page_url)
    tmpdir = "/tmp/runner"
    os.makedirs(tmpdir, exist_ok=True)
    out_path = os.path.join(tmpdir, fname)
    report({"status": "Mengunduh...", "clean_title": title, "percent": start_pct})
    total = 0
    if ".m3u8" in cdn.lower():
        total = download_hls(cdn, out_path, page_url, start_pct=start_pct)
    else:
        total = download_direct(cdn, out_path, page_url, start_pct=start_pct)
    if total < MIN_FILESIZE:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise Exception("Ukuran file terlalu kecil (< 5MB).")
    report({"status": "Upload ke Byse (via API)...", "percent": 80}, force=True)
    try:
        fc = byse_local_upload(out_path, title)
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
    info = byse_file_info(fc)
    url = byse_link(fc, info)
    size = info.get("size", "")
    hist = {
        "session_token": session_token,
        "email": "",
        "name": fname,
        "size": size or format_size(total),
        "time": wib(),
        "status": "success",
        "path": "",
        "drive_file_id": "",
        "byse_url": url,
        "thumb": "",
    }
    report({"status": "Selesai", "percent": 100, "downloaded": total, "total": total,
            "speed": 0, "clean_title": title, "status_text": "Berhasil disimpan ke Byse (via API).",
            "byse_url": url, "byse_filecode": fc}, hist, force=True)
    log(f"🎬 Selesai! File tersedia di Byse: {url}")

def get_token(session_token):
    r = requests.get(
        f"{API_BASE}/api/token/{session_token}",
        headers=_worker_headers(), timeout=20,
    )
    if r.status_code != 200:
        raise Exception(f"Token Google Drive tidak ditemukan (HTTP {r.status_code})")
    return r.json()

def put_token(session_token, token):
    r = requests.post(
        f"{API_BASE}/api/token/{session_token}",
        json=token,
        headers=_worker_headers(),
        timeout=20,
    )
    if r.status_code != 200:
        raise Exception(f"Gagal menyimpan token Google Drive (HTTP {r.status_code})")

def gh_put(path, content_b64):
    r = requests.get(f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
                     headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"},
                     timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None
    body = {"message": f"auto: {path}", "content": content_b64, "branch": GH_BRANCH}
    if sha:
        body["sha"] = sha
    r = requests.put(f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
                     headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json",
                              "Content-Type": "application/json"},
                     json=body, timeout=30)
    if r.status_code not in (200, 201):
        raise Exception(f"GH thumb upload: {r.status_code} {r.text[:150]}")


# ------------------------------------------------------------------ search
def clean_title_text(raw_title):
    if not raw_title:
        return ""
    cleaned = re.sub(r"(?i)javtiful|missav|njav|jav|123av", "", raw_title)
    return " ".join(cleaned.strip(" -|").split())


def validate_search_result(keyword, target_url):
    if not target_url:
        return False
    clean_url = target_url.split("#")[0].split("?")[0].lower()
    clean_kw = keyword.strip().lower()
    for word in ["tonton", "hd", "jav", "online", "sub", "indo", "streaming"]:
        clean_kw = clean_kw.replace(word, "")
    clean_kw = clean_kw.strip()
    if not clean_kw:
        return True
    slug_pattern = re.sub(r"[\s_]+", "-", clean_kw)
    return (slug_pattern in clean_url) or (re.sub(r"[\s\-_]+", "", clean_kw) in re.sub(r"[\s\-_]+", "", clean_url))


def search_javtiful(keyword):
    log(f"🔄 Alternatif 1 (Javtiful): '{keyword}'...")
    try:
        r = requests.get(f"https://javtiful.com/search?q={keyword.strip().replace(' ', '+')}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "/video/" in a["href"]:
                link = a["href"] if a["href"].startswith("http") else f"https://javtiful.com{a['href']}"
                if validate_search_result(keyword, link):
                    log("🎯 Ditemukan (Javtiful)"); return link
    except Exception as e:
        log(f"⚠️ Javtiful error: {e}")
    return None


def search_missav(keyword):
    log(f"🔄 Alternatif 2 (MissAV): '{keyword}'...")
    try:
        slug = keyword.strip().lower().replace(" ", "-")
        r = requests.get(f"https://missav.ws/id/search/{slug}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        invalid = ["/search/", "/actresses/", "/genres/", "/makers/", "/series/", "/new",
                   "/tags/", "/categories/", "english-subtitle", "uncensored", "/popular",
                   "/monthly", "playlist"]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("javascript") or href == "#" or "/id/" not in href:
                continue
            if any(x in href.lower() for x in invalid):
                continue
            full = href if href.startswith("http") else f"https://missav.ws{href}"
            if validate_search_result(keyword, full):
                log("🎯 Ditemukan (MissAV)"); return full
    except Exception as e:
        log(f"⚠️ MissAV error: {e}")
    return None


async def _njav_fetch(search_url):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True,
                                          args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0")
        page = await ctx.new_page()
        resp = await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)
        html = await page.content()
        await browser.close()
        return html if resp and resp.status != 404 else None


def search_njavtv(keyword):
    log(f"🔄 Alternatif 3 (NJAV TV): '{keyword}'...")
    slug = keyword.strip().lower()
    slug = re.sub(r"^(fc2)(ppv)", r"\1-\2", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    url = f"https://njavtv.com/id/search/{slug}"
    try:
        html = asyncio.new_event_loop().run_until_complete(_njav_fetch(url))
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("javascript") or href == "#" or slug not in href or "/search/" in href:
                    continue
                full = f"https://njavtv.com{href}" if href.startswith("/") else href
                if validate_search_result(keyword, full):
                    log("🎯 Ditemukan (NJAV)"); return full
    except Exception as e:
        log(f"⚠️ NJAV error: {e}")
    return None


def search_123av(keyword):
    slug = keyword.strip().lower().replace(" ", "-")
    return f"https://123av.com/id/v/{slug}"


async def sniper_extract_cdn(target_url):
    from playwright.async_api import async_playwright
    captured = []
    final_cdn = None
    translated_title = ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True,
                                              args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"])
            mobile = p.devices["iPhone 12 Pro"]
            ctx = await browser.new_context(**mobile)
            page = await ctx.new_page()

            async def on_response(resp):
                try:
                    if resp.request.resource_type in ("media", "fetch", "xhr"):
                        u = resp.url.lower()
                        valid = [".m3u8", ".mp4", ".ts", "master.json", "index.m3u8", ".m4s",
                                 "/hls/", "fast-stream", "/p/", "surrit.com", "wowstream2.cloud",
                                 "turbovidhls.com"]
                        ignore = [".svg", ".jpg", ".jpeg", ".png", ".gif", ".css", ".js",
                                  "thumbnail", "favicon", "plyr.io"]
                        ct = resp.headers.get("content-type", "").lower()
                        target = any(k in u for k in valid) or "video/" in ct or "mpegurl" in ct or "mp4" in ct
                        if target and not any(x in u for x in ignore) and "ping" not in u:
                            if resp.url not in captured:
                                captured.append(resp.url)
                except Exception:
                    pass

            page.on("response", on_response)
            log("Progres sedang berlangsung: 20%")
            r = await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            if r and r.status == 404:
                raise Exception("404.")
            log("Progres sedang berlangsung: 40%")
            try:
                t = clean_title_text(await page.title())
                if t:
                    try:
                        from deep_translator import GoogleTranslator
                        translated = GoogleTranslator(source="auto", target="id").translate(t) or t
                    except Exception:
                        translated = t
                    translated_title = translated
                    log(f"🏷️ Judul (ID): {translated_title}")
            except Exception:
                translated_title = "video_output"
            log("Progres sedang berlangsung: 75%")
            for sel in [".vjs-big-play-button", ".jw-icon-display", ".plyr__control--overlaid",
                        "button.play", ".play-button", "#player", "video", ".video-player"]:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    await el.click()
                    break
                except Exception:
                    continue
            for _ in range(12):
                await page.wait_for_timeout(1000)
                if any("master" in u or "_auto" in u or "fast-stream" in u or "/p/" in u
                       or "surrit.com" in u or "wowstream2.cloud" in u for u in captured if "ping" not in u):
                    break

            streams = [u for u in captured if "ping" not in u.lower()]
            if streams:
                wow = [u for u in streams if "wowstream2.cloud" in u.lower()]
                sur = [u for u in streams if "surrit.com" in u.lower()]
                master = [u for u in streams if "master" in u.lower() or "_auto" in u.lower()]
                token = [u for u in streams if "fast-stream" in u.lower() or "/p/" in u.lower()]
                mp4 = [u for u in streams if ".mp4" in u.lower()]
                if wow:
                    final_cdn = wow[0]
                elif sur:
                    key = lambda u: 3 if "1080" in u else 2 if "720" in u else 1 if "480" in u else 0
                    final_cdn = sorted(sur, key=key, reverse=True)[0]
                elif master:
                    final_cdn = master[0]
                elif token:
                    final_cdn = token[0]
                elif mp4:
                    final_cdn = mp4[0]
                else:
                    final_cdn = streams[0]
            log("Progres sedang berlangsung: 100%")
            await browser.close()
    except Exception as e:
        log(f"❌ Error Sniper: {str(e)}")
    return final_cdn, translated_title, target_url


def clean_filename(translated_title, fallback_url):
    if translated_title and translated_title != "video_output":
        name = "".join(c for c in translated_title if c.isalnum() or c in " -_").strip()
        if len(name) > 3:
            return name + ".mp4"
    slug = fallback_url.rstrip("/").split("/")[-1]
    slug = "".join(c for c in slug if c.isalnum() or c in "-_")
    return (slug if slug else "video_output") + ".mp4"


def format_size(b):
    b = float(b or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


# ------------------------------------------------------------------ download
def download_direct(url, out_path, referer, start_pct=0):
    hdr = {"User-Agent": "Mozilla/5.0", "Referer": referer or "https://123av.com/"}
    with requests.get(url, stream=True, timeout=30, headers=hdr, verify=False) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0) or 0)
        downloaded = 0
        start = time.time()
        report({"percent": start_pct, "speed": 0, "downloaded": 0, "total": total,
                "status": "Mengunduh ke runner..."}, force=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start
                raw = int(downloaded / total * 100) if total else 0
                pct = start_pct + int(raw * (100 - start_pct) / 100)
                report({"percent": pct, "speed": downloaded / elapsed,
                        "downloaded": downloaded, "total": total,
                        "status": "Mengunduh file fisik..."})
        return os.path.getsize(out_path)


def download_hls(url, out_path, referer, start_pct=0):
    hdr = "Referer: {}\r\nUser-Agent: Mozilla/5.0\r\n".format(referer or "https://123av.com/")
    report({"status": "Mengunduh HLS via ffmpeg...", "percent": start_pct}, force=True)
    cmd = ["ffmpeg", "-y", "-headers", hdr, "-i", url, "-c", "copy",
           "-bsf:a", "aac_adtstoasc", out_path]
    stderr_lines = []
    duration = None
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    last_pct = -1
    for line in proc.stderr:
        stderr_lines.append(line)
        if len(stderr_lines) > 400:
            stderr_lines = stderr_lines[-200:]
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", line)
        if m and duration is None:
            duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m2 = re.search(r"out_time=(\d+):(\d+):(\d+)\.(\d+)", line)
        if m2 and duration:
            ot = int(m2.group(1)) * 3600 + int(m2.group(2)) * 60 + int(m2.group(3))
            raw = int(ot / duration * 100)
            pct = start_pct + int(raw * (100 - start_pct) / 100)
            if pct != last_pct:
                last_pct = pct
                report({"percent": pct, "status": f"Mengunduh HLS... {pct}%"})
    proc.wait()
    if proc.returncode != 0:
        err = "".join(stderr_lines[-15:])
        raise Exception(f"ffmpeg HLS gagal: {err[:300]}")
    return os.path.getsize(out_path)


# ------------------------------------------------------------------ drive upload
def ensure_folder(service):
    q = f"name='{GDRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    r = service.files().list(q=q, spaces="drive", fields="files(id, name, parents)").execute()
    files = r.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": GDRIVE_FOLDER, "mimeType": "application/vnd.google-apps.folder"}
    f = service.files().create(body=meta, fields="id").execute()
    return f["id"]


def upload_drive(file_path, token, session_token, start_pct=0):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request as GoogleRequest

    creds = Credentials(
        token=token.get("access_token"), refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token.get("client_id"), client_secret=token.get("client_secret"),
        scopes=[GDRIVE_SCOPE],
    )
    if creds.expired:
        try:
            creds.refresh(GoogleRequest())
        except Exception as e:
            raise Exception(f"Refresh token gagal: {e}")
    service = build("drive", "v3", credentials=creds)
    folder_id = ensure_folder(service)
    name = os.path.basename(file_path)
    meta = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="application/octet-stream",
                            chunksize=5 * 1024 * 1024, resumable=True)
    req = service.files().create(body=meta, media_body=media, fields="id")
    resp = None
    last = -1
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            raw = int(status.progress() * 100)
            pct = start_pct + int(raw * (100 - start_pct) / 100)
            if pct != last:
                last = pct
                report({"percent": pct, "status": f"Mengunggah ke Drive... {pct}%"})
            if raw in (50, 90):
                try:
                    put_token(session_token, {
                        "access_token": creds.token, "refresh_token": creds.refresh_token,
                        "client_id": token.get("client_id"), "client_secret": token.get("client_secret"),
                        "scopes": [GDRIVE_SCOPE],
                    })
                except Exception:
                    pass
    try:
        put_token(session_token, {
            "access_token": creds.token, "refresh_token": creds.refresh_token,
            "client_id": token.get("client_id"), "client_secret": token.get("client_secret"),
            "scopes": [GDRIVE_SCOPE],
        })
    except Exception:
        pass
    return resp["id"]


def make_thumbnail(video_path, jpg_path):
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", "00:00:03", "-i", video_path, "-vframes", "1",
                        "-vf", "scale=160:-1", jpg_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        return os.path.exists(jpg_path)
    except Exception:
        return False


def thumb_gh_name(filename):
    import hashlib
    return hashlib.sha256(filename.encode()).hexdigest()[:16] + ".jpg"


def peek_media_size(cdn, referer=None):
    """Cukup intip header CDN untuk tahu ukuran video — TANPA unduh penuh.
    HEAD dulu, fallback GET Range bytes=0-0 (Content-Range), lalu content-length."""
    hdr = {"User-Agent": "Mozilla/5.0"}
    if referer:
        hdr["Referer"] = referer
    try:
        rh = requests.get(cdn, headers=hdr, timeout=25, verify=False,
                          allow_redirects=True, stream=True)
        rh.close()
        b = int(rh.headers.get("content-length") or 0)
        if b:
            return format_size(b)
    except Exception as e:
        log(f"⚠️ Preview size error (HEAD): {e}")
    try:
        rg = requests.get(cdn, headers=dict(hdr, Range="bytes=0-0"), timeout=25,
                          verify=False, allow_redirects=True, stream=True)
        rg.close()
        cr = rg.headers.get("content-range", "")
        m = re.search(r"/(\d+)\s*$", cr)
        if m and int(m.group(1)):
            return format_size(int(m.group(1)))
        b = int(rg.headers.get("content-length") or 0)
        if b:
            return format_size(b)
    except Exception as e:
        log(f"⚠️ Preview size error (Range): {e}")
    return "—"


def probe_media_duration(cdn, referer=None):
    """Durasi akurat via ffprobe (baca metadata/playlist saja, tidak unduh penuh).
    Fallback: string kosong → dipakai durasi dari meta halaman."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1"]
        if referer:
            cmd += ["-headers", f"Referer: {referer}\r\nUser-Agent: Mozilla/5.0\r\n"]
        cmd += [cdn]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        s = out.stdout.strip()
        if not s:
            # ffprobe makan 200/redirect tapi tak bisa baca durasi (CDN kunci /
            # playlist tidak probeable). Bukan error — pakai fallback meta halaman.
            return ""
        try:
            dur = float(s)
        except ValueError:
            log(f"⚠️ Probe duration: output ffprobe bukan angka: {s[:60]!r}")
            return ""
        if dur > 0:
            hh, rem = divmod(int(dur), 3600)
            mi, ss = divmod(rem, 60)
            return f"{hh}:{mi:02d}:{ss:02d}"
    except subprocess.TimeoutExpired as e:
        log(f"⚠️ Probe duration timeout: {e}")
    except OSError as e:
        log(f"⚠️ ffprobe tidak tersedia atau gagal: {e}")
    return ""


def fetch_preview_metadata(page_url, cdn, title):
    """Scrape metadata untuk preview TANPA mengunduh penuh:
    thumb (og:image / video poster), size (HEAD/Range CDN — intip header saja),
    duration (ffprobe; fallback durasi dari meta halaman)."""
    preview = {"title": title or "", "filename": "", "thumb": "", "size": "—", "duration": ""}
    html_dur = ""
    try:
        r = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            og = (soup.find("meta", property="og:image")
                  or soup.find("meta", attrs={"name": "og:image"}))
            if og and og.get("content"):
                preview["thumb"] = og["content"]
            if not preview["thumb"]:
                vid = soup.find("video")
                if vid and vid.get("poster"):
                    preview["thumb"] = vid["poster"]
            dur = None
            m = (soup.find("meta", property="video:duration")
                 or soup.find("meta", attrs={"name": "video:duration"}))
            if m and m.get("content"):
                try:
                    dur = int(float(m["content"]))
                except Exception:
                    dur = None
            if dur is None:
                for pat in [r"(\d{1,2}):(\d{2}):(\d{2})", r"(\d{1,2})\s*(?:j[au]m)?\s*(\d{2})\s*(?:m[ae]n?it)?\s*(\d{2})\s*s",
                            r"\b(\d{1,2}):(\d{2})\b(?!:)"]:
                    mm = re.search(pat, r.text)
                    if mm:
                        try:
                            g = mm.groups()
                            if len(g) == 3:
                                hh, mi, ss = (int(x) for x in g)
                            else:
                                hh, mi, ss = 0, int(g[0]), int(g[1])
                            dur = hh * 3600 + mi * 60 + ss
                        except Exception:
                            dur = None
                        if dur:
                            break
            if dur:
                hh, rem = divmod(dur, 3600)
                mi, ss = divmod(rem, 60)
                html_dur = f"{hh}:{mi:02d}:{ss:02d}"
    except Exception as e:
        log(f"⚠️ Preview metadata error: {e}")
    if cdn:
        preview["size"] = peek_media_size(cdn, page_url)
        duration = probe_media_duration(cdn, page_url)
        preview["duration"] = duration or html_dur
    else:
        preview["duration"] = html_dur
    return preview


# ------------------------------------------------------------------ main
def wait_for_confirmation(timeout=WAIT_CONFIRM_TIMEOUT):
    """Setelah preview_ready, worker run yang SAMA menunggu user menekan
    'Unduh ke Google Drive' (confirmed=True) — TANPA re-run/dispatch baru.
    Return True bila dikonfirmasi, False bila waktu tunggu habis."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = get_task()
        except Exception:
            st = {}
        dest = str(st.get("destination") or "").lower()
        byse = st.get("byse") or {}
        # Tujuan non-drive telanjur ditangani BACKEND/run lain → worker ini WAJIB
        # pulang cepat (jangan unduh → jangan upload Google Drive, jangan dobel kerjain).
        if dest == "direct" and st.get("direct_url"):
            log("📥 Tujuan 'direct' diproses backend (link CDN dikirim ke browser) — worker selesai.")
            return False
        if dest == "byse" and (byse.get("filecode") or byse.get("status") in ("working", "done", "remote_error")):
            log("🎬 Tujuan 'byse' ditangani backend/worker baru — worker ini selesai.")
            return False
        if bool(st.get("confirmed")):
            log("✅ Konfirmasi unduhan diterima — melanjutkan unduh penuh di run yang sama.")
            return True
        remaining = int(deadline - time.time())
        if remaining > 0 and remaining % 60 == 0:
            log(f"⏳ Menunggu konfirmasi unduhan... (sisa {remaining // 60} menit)")
        time.sleep(CONFIRM_POLL_INTERVAL)
    log("⏳ Waktu tunggu konfirmasi habis — preview dibatalkan, tidak ada unduhan penuh.")
    return False


def run_test_sim(raw_input):
    """Simulasi lengkap alur UI/backend TANPA login (task bertanda TEST).

    Menggantikan scraping + Google Drive dengan fase sintetis agar UI bisa
    diverifikasi end-to-end: log real-time, step GitHub, bar progres, panel
    preview, tombol konfirmasi, hingga panel Selesai."""
    base = str(raw_input)
    st = get_task()
    confirmed = bool(st.get("confirmed"))
    mode = str(st.get("mode") or "").lower()
    if confirmed or mode == "download":
        _simulate_download_phase(base)
        return

    log("🧪 MODE TEST — simulasi alur UI/backend (tanpa login Google Drive)")
    log(f"📁 Google Drive folder: '{GDRIVE_FOLDER}' | Mode: TEST (PREVIEW)")
    for p in (20, 40, 60, 75, 100):
        report({"status": "Memproses pencarian...", "percent": p, "clean_title": f"[TEST] {base}"}, force=True)
        log(f"Progres sedang berlangsung: {p}%")
        log(f"🔄 [TEST] Simulasi pencarian/metadata {p}%...")
        time.sleep(1.2)
    fname = f"{base} - preview-test.mp4"
    preview = {
        "title": f"{base} — Sampel UI (TEST)",
        "filename": fname,
        "size": "512 MB",
        "duration": "1:38:45",
        "format": "1080p",
        "thumb": "",
    }
    log(f"🖼️ Preview: {fname} (TEST)")
    report({
        "status": "preview_ready",
        "percent": 100,
        "clean_title": f"[TEST] {base}",
        "preview": preview,
        "confirmed": False,
        "mode": "preview",
    }, force=True)
    log("✅ Preview siap (TEST). Klik 'Unduh ke Google Drive' untuk menguji alur konfirmasi.")
    if not wait_for_confirmation():
        log("⏳ TIME-OUT (TEST) — preview dibiarkan; gunakan tombol Reset di UI untuk membersihkan.")
        return
    _simulate_download_phase(base)


def _simulate_download_phase(base):
    log("📦 [TEST] Konfirmasi diterima — mensimulasikan unduh penuh + upload ke Drive...")
    for p in (20, 45, 70, 90, 100):
        report({"status": "Mengunduh (TEST)...", "percent": p, "clean_title": f"[TEST] {base}"}, force=True)
        log(f"Progres sedang berlangsung: {p}%")
        log(f"⬇️ [TEST] Mengunduh & mengunggah {p}%...")
        time.sleep(1.0)
    report({"status": "Selesai", "percent": 100, "downloaded": 1, "total": 1, "speed": 0,
            "clean_title": f"[TEST] {base}"}, None, force=True)
    log("🏁 Selesai (TEST) — alur konfirmasi → Selesai berhasil diverifikasi. Task tetap bisa di-reset dari UI.")


def run():
    global task_id
    # GitHub Actions supplies TASK_ID from repository_dispatch/workflow_dispatch.
    # argv[1] remains supported for manual/local execution.
    task_id = (os.environ.get("TASK_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
    if not task_id:
        raise RuntimeError("TASK_ID tidak ditemukan. GitHub Actions harus mengirim task_id.")

    st = get_task()
    raw_input = st.get("id", task_id)
    session_token = st.get("session_token", "")
    confirmed = bool(st.get("confirmed"))
    mode = str(st.get("mode") or ("download" if confirmed else "preview")).lower()
    is_preview = mode == "preview" and not confirmed
    dest0 = str(st.get("destination") or (st.get("meta") or {}).get("destination") or "").lower()

    report({"status": "Memproses pencarian...", "percent": 0},
           {"id": task_id}, force=True)

    _ctx = github_context()
    if _ctx:
        log(f"▶️ GitHub Action: run #{_ctx.get('run_number') or _ctx.get('run_id')} — {_ctx.get('html_url')} (job: {_ctx.get('job')})")

    log(f"🔍 Menerima input: '{raw_input}'")
    # MODE TEST: task bertanda TEST (code berawalan 'TEST' atau meta.test=true) →
    # jalankan simulasi UI/backend TANPA login Google Drive.
    if bool(st.get("test")) or str(raw_input).upper().startswith("TEST"):
        run_test_sim(raw_input)
        return
    log(f"📁 Google Drive folder: '{GDRIVE_FOLDER}' | Mode: {'PREVIEW' if is_preview else 'DOWNLOAD'}")
    if not session_token:
        report({"status": "Gagal: harus login Google Drive"}, force=True)
        raise RuntimeError("Sesi Google Drive tidak terhubung (login ulang di UI) — menandai run GitHub Actions sebagai FAILURE")

    token = None
    if not is_preview and dest0 not in ("byse", "direct"):
        token = get_token(session_token)
        if not token:
            report({"status": "Gagal: sesi Drive tidak valid"}, force=True)
            raise RuntimeError("Sesi Google Drive tidak valid (login ulang) — menandai run GitHub Actions sebagai FAILURE")

    log("Progres sedang berlangsung: 20%")

    actual = raw_input
    if not (raw_input.startswith("http://") or raw_input.startswith("https://")):
        actual = (search_javtiful(raw_input) or search_missav(raw_input)
                  or search_njavtv(raw_input) or search_123av(raw_input))
        report({"status": "Memproses pencarian..."})
    if not actual:
        raise Exception(f"Gagal mendapatkan URL target untuk '{raw_input}'")
    if "123av.com" not in actual and not validate_search_result(raw_input, actual):
        raise Exception("Regex Mismatch Error!")

    log("🔗 Mengakses halaman utama")
    cdn, title, page_url = asyncio.new_event_loop().run_until_complete(sniper_extract_cdn(actual))
    if not cdn:
        raise Exception("Gagal membongkar link CDN video.")

    fname = clean_filename(title, page_url)
    log(f"📦 File target: {fname}")

    # RUN FALLBACK (auto-dispatch saat byse remote gagal di tengah): meta sudah
    # destination='byse' → langsung tangani tujuan byse (refresh CDN + remote,
    # fallback unduh+upload lokal), tanpa menunggu konfirmasi UI.
    if dest0 == "byse":
        log("🎬 Tujuan byse (fallback/auto): remote via API → fallback unduh+upload lokal bila perlu.")
        run_byse_destination(cdn, page_url, title, session_token)
        return

    if is_preview:
        # MODE PREVIEW: scrape metadata SAJA, jangan unduh penuh.
        preview = fetch_preview_metadata(page_url, cdn, title)
        preview["filename"] = fname
        log(f"🖼️ Preview: {fname} | size={preview['size']} | durasi={preview['duration'] or '—'}")
        report({
            "status": "preview_ready",
            "percent": 100,
            "clean_title": title,
            "preview": preview,
            "cdn": cdn,
            "page_url": page_url,
            "confirmed": False,
            "mode": "preview",
        }, force=True)
        log("✅ Preview siap — pilih tujuan: Google Drive, Byse (via API), atau Unduh Langsung.")
        # Tunggu konfirmasi user di run yang SAMA (jangan re-dispatch/restart).
        if not wait_for_confirmation():
            return  # exit 0
        # Tujuan selain Google Drive ditangani oleh backend (Byse via API /
        # unduh langsung) — worker selesai tanpa unduh lokal. Hanya mode 'drive'
        # yang melanjutkan unduh penuh + upload ke Drive.
        after_confirmed = get_task()
        dest = str((after_confirmed.get("meta") or {}).get("destination") or "").lower()
        if dest == "byse":
            run_byse_destination(cdn, page_url, title, session_token)
            return
        if dest == "direct":
            log("📥 Tujuan 'direct': link CDN dikirim ke browser — worker selesai.")
            return
        token = get_token(session_token)
        if not token:
            report({"status": "Gagal: sesi Drive tidak valid"}, force=True)
            raise RuntimeError("Sesi Google Drive tidak valid (login ulang) — menandai run GitHub Actions sebagai FAILURE")
        log("📦 Melanjutkan unduh penuh di run yang sama — progres tidak di-reset.")

    start_pct = 20 if is_preview else 0

    tmpdir = "/tmp/runner"
    os.makedirs(tmpdir, exist_ok=True)
    out_path = os.path.join(tmpdir, fname)

    report({"status": "Mengunduh...", "clean_title": title, "percent": start_pct})
    total = 0
    if ".m3u8" in cdn.lower():
        total = download_hls(cdn, out_path, page_url, start_pct=start_pct)
    else:
        total = download_direct(cdn, out_path, page_url, start_pct=start_pct)
    if total < MIN_FILESIZE:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise Exception("Ukuran file terlalu kecil (< 5MB).")

    report({"status": "Mempersiapkan upload ke Drive...", "percent": start_pct}, force=True)
    drive_id = upload_drive(out_path, token, session_token, start_pct=start_pct)
    log(f"✅ File diupload ke Drive (ID: {drive_id})")

    thumb = None
    try:
        jpg = os.path.join(tmpdir, thumb_gh_name(fname))
        if make_thumbnail(out_path, jpg) and GH_TOKEN and GH_REPO:
            with open(jpg, "rb") as f:
                gh_put(f"data/thumbs/{thumb_gh_name(fname)}",
                       base64.b64encode(f.read()).decode())
            thumb = thumb_gh_name(fname)
            log("🖼️ Thumbnail berhasil disimpan.")
    except Exception as e:
        log(f"⚠️ Thumbnail gagal: {e}")

    if os.path.exists(out_path):
        os.remove(out_path)

    hist = {
        "session_token": session_token,
        "email": "",  # diisi ulang oleh Vercel dari sessions
        "name": fname,
        "size": format_size(total),
        "time": wib(),
        "status": "success",
        "path": "",
        "drive_file_id": drive_id,
        "thumb": thumb,
    }
    report({"status": "Selesai", "percent": 100, "downloaded": total, "total": total,
            "speed": 0, "clean_title": title}, hist, force=True)
    log("🏁 Selesai!")


if __name__ == "__main__":
    try:
        if not API_BASE or not WORKER_SECRET:
            print("API_BASE & WORKER_SECRET wajib di-set.", flush=True)
            sys.exit(1)
        run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            report({"status": f"Gagal: {e}", "percent": 0}, force=True)
        except Exception:
            pass
        sys.exit(1)
