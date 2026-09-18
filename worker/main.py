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
        body["task"]["logs"] = _report_queue[:100]
        _report_queue.clear()
    if task_fields:
        body["task"].update(task_fields)
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
