# Vivern MC - Automated Birthday Audio Production Service
**Telegram Mini App & Bot • Version 1.0 (Audio-Only Initial Release)**

Vivern MC is a privately owned Telegram service that allows customers to upload an original Uzbek birthday phone-call recording and the birthday person's special music. The system analyses the conversation using AI, dynamically arranges and mixes opening telephone sound effects, starter music, birthday wishes music, call ending music, and appends the special music outro, delivering the finished production directly to the customer's Telegram chat.

---

## Architecture Overview

```
                      ┌──────────────────────┐
                      │ Telegram Bot & Chat  │
                      │   (@VivernMC_Bot)    │
                      └──────────┬───────────┘
                                 │
                   Launch Mini App / Deliver MP3
                                 │
                      ┌──────────▼───────────┐
                      │  Telegram Mini App   │
                      │  (FastAPI + WebApp)  │
                      └──────────┬───────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
 ┌──────────▼─────────┐ ┌────────▼─────────┐ ┌────────▼─────────┐
 │ Protected Admin    │ │ Speech Analysis  │ │ 5-Stage FFmpeg   │
 │ Track Library (4)  │ │ (Uzbek STT/LLM)  │ │ Audio Engine     │
 └────────────────────┘ └──────────────────┘ └──────────────────┘
```

### 5-Stage Audio Arrangement Pipeline
1. **Call Opening**: Telephone keypad/number-pressing and call/ringing sound effects.
2. **Starter**: Original phone speech + Starter background music (voice-priority ducking).
3. **Birthday Wishes**: Original phone speech + Wishes background music (smooth crossfade).
4. **Call Ending**: Original phone speech + Call Ending background music.
5. **Special Music Outro**: Birthday owner's favorite song appended after call completion with a smooth fade-out.

---

## 4 Managed Sound Categories (Admin Library)
Only administrators (`ADMIN_TELEGRAM_IDS`) can upload and manage these library assets:
- **`number_call`**: Telephone keypad & ringing FX.
- **`starter`**: Opening conversation background music.
- **`wishes`**: Birthday wishes background music.
- **`call_ending`**: Call farewell and ending background music.

---

## Quick Start & Local Execution

### 1. Requirements
- Python 3.10+ (Tested on Python 3.12.8)
- FFmpeg (Automatically provided via `imageio_ffmpeg` static binary)

### 2. Configuration
Copy `.env.example` to `.env` and fill in your variables:
```bash
cp .env.example .env
```
Key configuration settings in `.env`:
- `TELEGRAM_BOT_TOKEN`: Provided Telegram Bot token.
- `ADMIN_TELEGRAM_IDS`: Comma-separated Telegram User IDs permitted as admins (e.g. `8449563084`).
- `DATABASE_URL`: `sqlite+aiosqlite:///storage/vivern.db` for local dev or `postgresql+asyncpg://...` for production.
- `SPEECH_PROVIDER`: `mock` for local/offline testing, or `google_chirp` for live Google Cloud STT V2.
- `ANALYSIS_PROVIDER`: `heuristic` for keyword-based classification, or `openai` for OpenAI gpt-4o-mini.
- `PRICE_PER_ORDER_SOM`: `5000` (First 5 orders free per user account).

### 3. Run the Service
To start the FastAPI backend, static Mini App server, and the Telegram bot polling concurrently:
```bash
python run_server.py
```
- Customer Mini App: `http://localhost:8000/index.html`
- Protected Admin Panel: `http://localhost:8000/admin.html`
- API Health Check: `http://localhost:8000/api/health`

### 4. Run Acceptance Tests
To execute all 15 acceptance criteria (AT-01 to AT-15):
```bash
python -m backend.tests.test_master_acceptance
```

---

## Acceptance Test Suite (AT-01 to AT-15)

| Test ID | Criterion | Status |
| :--- | :--- | :--- |
| **AT-01** | **Telegram Launch**: Mini App opens; backend verifies HMAC-SHA256 `initData`. | ✅ PASS |
| **AT-02** | **Admin Protection**: Non-admin customer gets 403 Forbidden; admin allowed. | ✅ PASS |
| **AT-03** | **Library Management**: Admin manages all 4 categories, validates media, and previews tracks. | ✅ PASS |
| **AT-04** | **Upload Scope**: Customer uploads only Original Recording and Special Music. | ✅ PASS |
| **AT-05** | **Variable Length**: Short and long recordings dynamically arranged without hardcoded timestamps. | ✅ PASS |
| **AT-06** | **Uzbek Transcript**: Timestamped Uzbek transcript segments returned. | ✅ PASS |
| **AT-07** | **Stage Detection**: Wishes & ending sections classified; low confidence flagged with warnings. | ✅ PASS |
| **AT-08** | **Mix Quality**: Speech intelligible with voice priority ducking (-16dB BG music) and smooth fades. | ✅ PASS |
| **AT-09** | **Special Music Outro**: Customer's song appended after speech with configured fade. | ✅ PASS |
| **AT-10** | **Telegram Delivery**: Exactly one output audio delivered directly to customer's bot chat. | ✅ PASS |
| **AT-11** | **Order History Isolation**: Customers see only their own orders. | ✅ PASS |
| **AT-12** | **Failure Handling**: Failed jobs do not consume free trial generations. | ✅ PASS |
| **AT-13** | **Secrets Isolation**: No tokens or keys in frontend, Git, or logs. | ✅ PASS |
| **AT-14** | **Background Worker Queue**: Closing Mini App does not stop background processing. | ✅ PASS |
| **AT-15** | **Cost Tracking**: Per-order compute time, speech minutes, and storage tracked. | ✅ PASS |

---

## Production Deployment & Operational Guidance

### 1. Production PostgreSQL Database
Update `DATABASE_URL` in `.env`:
```
DATABASE_URL=postgresql+asyncpg://vivern_user:your_password@localhost:5432/vivern_mc
```

### 2. Telegram WebApp Setup
1. In Telegram, talk to [@BotFather](https://t.me/BotFather):
   - Command: `/setmenubutton`
   - Select `@VivernMC_Bot`
   - Set URL: `https://yourdomain.com/` (or ngrok/tunnel HTTPS URL)
2. Use HTTPS: Telegram requires all WebApps to be served via valid SSL/TLS certificates.

### 3. Database Backup & Restore
- **SQLite**:
  ```bash
  sqlite3 storage/vivern.db ".backup 'storage/backup_$(date +%Y%m%d).db'"
  ```
- **PostgreSQL**:
  ```bash
  pg_dump -U vivern_user vivern_mc > vivern_mc_backup.sql
  psql -U vivern_user vivern_mc < vivern_mc_backup.sql
  ```

### 4. File Retention Policy
Run periodic retention cleanup via cron or scheduled task:
```python
from backend.app.services.storage.retention import cleanup_expired_files
cleanup_expired_files(retention_days=30)
```
