# puppeter-web — Remote Uploader (Vercel + GitHub Actions)

Port lengkap dari project `puppeter` (Colab) menjadi arsitektur cloud:

- **Vercel** = UI (FastAPI) + API + koordinasi state (via GitHub API)
- **GitHub Actions** = eksekusi tugas berat (scrape Playwright, download ffmpeg/HLS, upload Google Drive)

## Cara kerja

```
User (UI Vercel)
   │  masukkan kode (mis. "vema 263")
   ▼
/api/download ──► tulis task ke data/state.json (GitHub) ──► repository_dispatch
   ▲                                                              │
   │                                                              ▼
  UI polling /api/progress ──► state.json  ◄──  GH Actions worker (worker/main.py)
   ▲                                                              │
   └────────────── berulang (progress/log/status) ◄───────────────┘
```

- `data/state.json` — koordinasi tasks + history + sessions (ditulis bot via GitHub API).
- `data/tokens/*.enc` — token Google Drive terenkripsi (Fernet, kunci dari `API_ENC_KEY`).
- `data/pending/*.json` — state device-flow OAuth agar tahan cold-start serverless.
- `data/thumbs/*.jpg` — thumbnail riwayat (ditulis worker).
- `data/suggestions.json` — saran acak (diekstrak dari javdb.sql).

## Struktur

```
.
├── api/index.py            # FastAPI (UI + API + koordinasi GitHub + token GDrive)
├── ui/html.py              # UI (port dari uihtml.py)
├── ui/modal.py             # Modal UI
├── worker/main.py          # Worker: search → sniper CDN → download (mp4/HLS) → upload GDrive
├── worker/requirements.txt
├── scripts/generate_suggestions.py
├── .github/workflows/jav-task.yml
└── vercel.json
```

## Setup

### 1. Repository & secrets (GitHub)

Dibutuhkan PAT (classic, scope `repo` + `workflow`) sebagai `GH_TOKEN` — dipakai Vercel
untuk menulis state/dispatch dan worker untuk commit thumbnail.

Repo secrets:
| Secret | Keterangan |
|---|---|
| `GH_TOKEN` | PAT dengan scope `repo` (+ `workflow`) |
| `GH_REPO` | `owner/repo` |
| `WORKER_SECRET` | string rahasia bersama Vercel ↔ worker |
| `API_BASE` | URL publik Vercel, mis. `https://xxx.vercel.app` |

Repo variables (opsional):
| Variable | Keterangan |
|---|---|
| `GH_BRANCH` | default `main` |
| `GDRIVE_FOLDER` | folder tujuan di Drive, default `javColab` |

### 2. Vercel

Env vars di Vercel:

| Env | Keterangan |
|---|---|
| `GH_TOKEN` | PAT GitHub (sama seperti secret repo) |
| `GH_REPO` | `owner/repo` |
| `GH_BRANCH` | `main` |
| `WORKER_SECRET` | sama dengan secret repo |
| `API_ENC_KEY` | kunci Fernet (opsional; jika kosong dibuat deterministik) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth Client Google (Device flow) |
| `API_BASE` | URL publik Vercel sendiri |

Deploy:

```bash
vercel --prod
```

### 3. Alur akses

1. Buka UI → **Hubungkan Drive** → otorisasi Google (device flow).
2. Masukkan kode video (bukan URL) → worker GitHub Actions mulai.
3. Pantau progres/log di UI; hasil masuk ke Google Drive → `javColab`.
4. Riwayat tampil di tab **Riwayat Unduhan** (dengan thumbnail & link preview Drive).

## Ekstraksi saran dari javdb.sql

```bash
python scripts/generate_suggestions.py /path/javdb.sql   # → data/suggestions.json
```

## Catatan

- Task berjalan serial (concurrency group `jav-worker`). 
- Hanya input KODE yang diterima UI (logika asli menolak URL).
- Tanpa login Google Drive, worker menolak task (sesuai perilaku asli).