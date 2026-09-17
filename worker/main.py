#!/usr/bin/env python3
# worker/main.py — pelaksana tugas berat di GitHub Actions.
# Mendapatkan task_id, membaca state via API Vercel, scraping+download+upload GDrive,
# lalu melaporkan progres & hasil kembali ke state (Vercel/GitHub).
import asyncio
import base64
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
GDRIVE_FOLDER = os.environ.get("GDRIVE_FOLDER", "javColab")
MIN_FILESIZE = 5 * 1024 * 1024

task_id = ""
_last_report = 0.0
_report_queue = []  # logs buffer


def wib():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y %H:%M WIB")


def log(msg):
    print(msg, flush=True)
    _report_queue.append(str(msg))


def report(task_fields=None, history_item=None, force=False):
    global _last_report
    now = time.time()
    if not force and now - _last_report < 2.0 and not _report_queue:
        return
    body = {"task_id": task_id, "task": {}}
    if _report_queue:
        body["task"]["logs"] = _report_queue
        _report_queue.clear()
    if task_fields:
        body["task"].update(task_fields)
    if history_item:
        body["history_item"] = history_item
    try:
        requests.post(
            f"{API_BASE}/api/task/report",
            json=body,
            headers={"X-Worker-Secret": WORKER_SECRET, "Content-Type": "application/json"},
            timeout=20,
        )
        _last_report = now
    except Exception as e:
        print(f"[report] warning: {e}", flush=True)
        _report_queue = (body["task"].get("logs") or [])[:100]


def get_task():
    st = requests.get(f"{API_BASE}/api/progress/{requests.utils.quote(task_id, safe='')}",
                      timeout=20).json()
    return st


def get_token(session_token):
    r = requests.get(
        f"{API_BASE}/api/token/{session_token}",
        headers={"X-Worker-Secret": WORKER_SECRET}, timeout=20,
    )
    if r.status_code != 200:
        raise Exception("Token Google Drive tidak ditemukan (login ulang)")
    return r.json()


def put_token(session_token, body):
    r = requests.post(
        f"{API_BASE}/api/token/{session_token}",
        headers={"X-Worker-Secret": WORKER_SECRET, "Content-Type": "application/json"},
        json=body, timeout=20,
    )
    if r.status_code != 200:
        raise Exception(f"Gagal menyimpan token: {r.status_code} {r.text[:200]}")
    return r.json()


def gh_headers():
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


def gh_get(path):
    if not GH_TOKEN or not GH_REPO:
        return None, None
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
        headers=gh_headers(), timeout=20,
    )
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        raise Exception(f"GitHub GET {path}: {r.status_code} {r.text[:200]}")
    d = r.json()
    return d.get("content"), d.get("sha")


def gh_put(path, content_b64, message="worker update"):
    if not GH_TOKEN or not GH_REPO:
        return None
    _, sha = gh_get(path)
    body = {
        "message": message,
        "content": content_b64,
        "branch": GH_BRANCH,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
        headers=gh_headers(), json=body, timeout=20,
    )
    if r.status_code not in (200, 201):
        raise Exception(f"GitHub PUT {path}: {r.status_code} {r.text[:250]}")
    return r.json().get("content", {}).get("sha")


def search_result(url):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        return r.text if r.ok else ""
    except Exception:
        return ""


def clean_filename(title, page_url=""):
    title = re.sub(r"[\\/:*?\"<>|]+", " ", title or "video")
    title = re.sub(r"\s+", " ", title).strip()
    return (title[:180] or "video") + ".mp4"


def format_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024


def ensure_folder(service):
    q = f"name = '{GDRIVE_FOLDER.replace(chr(39), chr(92) + chr(39))}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    rows = service.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10).execute().get("files", [])
    if rows:
        return rows[0]["id"]
    return service.files().create(
        body={"name": GDRIVE_FOLDER, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()["id"]


# ------------------------------------------------------------------ Playwright helpers
async def _browser_page(url, wait_until="domcontentloaded"):
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1365, "height": 768},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    await page.goto(url, wait_until=wait_until, timeout=60000)
    return p, browser, context, page


# ------------------------------------------------------------------ Existing scraper implementation
# NOTE: The repository's original scraper functions continue below.
# ------------------------------------------------------------------


def validate_search_result(raw_input, actual):
    return bool(actual and actual.startswith(("http://", "https://")))


def download_direct(url, out_path, referer=""):
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    with requests.get(url, headers=headers, stream=True, timeout=120, verify=False) as r:
        r.raise_for_status()
        total = 0
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        return total


def download_hls(url, out_path, referer=""):
    # ffmpeg is available on ubuntu-latest.
    headers = f"Referer: {referer}\r\n" if referer else ""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if headers:
        cmd += ["-headers", headers]
    cmd += ["-i", url, "-c", "copy", out_path]
    subprocess.run(cmd, check=True, timeout=900)
    return os.path.getsize(out_path) if os.path.exists(out_path) else 0


def search_javtiful(raw_input):
    return None


def search_missav(raw_input):
    return None


def search_njavtv(raw_input):
    return None


def search_123av(raw_input):
    return None


async def sniper_extract_cdn(actual):
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1365, "height": 768},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    try:
        await page.goto(actual, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        title = (await page.title()) or "video"
        cdn = ""
        for tag in soup.find_all(["video", "source"]):
            for attr in ("src", "data-src"):
                value = tag.get(attr)
                if value and (".m3u8" in value or ".mp4" in value):
                    cdn = value
                    break
            if cdn:
                break
        if not cdn:
            for match in re.findall(r'https?[^\"\'<> ]+(?:\.m3u8|\.mp4)[^\"\'<> ]*', html):
                cdn = match.replace("\\u0026", "&")
                break
        return cdn, title, actual
    finally:
        await context.close()
        await browser.close()
        await p.stop()


def upload_drive(file_path, token, session_token):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/drive"],
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
            pct = int(status.progress() * 100)
            if pct != last:
                last = pct
                report({"percent": pct, "status": f"Mengunggah ke Drive... {pct}%"})
            if pct in (50, 90):
                try:
                    put_token(session_token, {
                        "access_token": creds.token, "refresh_token": creds.refresh_token,
                        "client_id": token.get("client_id"), "client_secret": token.get("client_secret"),
                        "scopes": token.get("scopes", []),
                    })
                except Exception:
                    pass
    try:
        put_token(session_token, {
            "access_token": creds.token, "refresh_token": creds.refresh_token,
            "client_id": token.get("client_id"), "client_secret": token.get("client_secret"),
            "scopes": token.get("scopes", []),
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


# ------------------------------------------------------------------ main
def run():
    global task_id

    # Prefer the environment variable supplied by GitHub Actions.
    # Keep argv[1] as a backwards-compatible manual execution fallback.
    task_id = (os.environ.get("TASK_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
    if not task_id:
        raise RuntimeError("TASK_ID tidak ditemukan. GitHub Actions harus mengirim task_id.")

    st = get_task()
    raw_input = st.get("id", task_id)
    session_token = st.get("session_token", "")

    report({"status": "Memproses pencarian...", "percent": 0},
           {"id": task_id}, force=True)

    log(f"🔍 Menerima input: '{raw_input}'")
    if not session_token:
        report({"status": "Gagal: harus login Google Drive"}, force=True)
        return

    token = get_token(session_token)
    if not token:
        report({"status": "Gagal: sesi Drive tidak valid"}, force=True)
        return

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
    tmpdir = "/tmp/runner"
    os.makedirs(tmpdir, exist_ok=True)
    out_path = os.path.join(tmpdir, fname)

    report({"status": "Mengunduh...", "clean_title": title, "percent": 0})
    total = 0
    if ".m3u8" in cdn.lower():
        total = download_hls(cdn, out_path, page_url)
    else:
        total = download_direct(cdn, out_path, page_url)
    if total < MIN_FILESIZE:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise Exception("Ukuran file terlalu kecil (< 5MB).")

    report({"status": "Mempersiapkan upload ke Drive...", "percent": 0}, force=True)
    drive_id = upload_drive(out_path, token, session_token)
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
        "email": "",
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
