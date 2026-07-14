# AutoShorts-Engine
_An autonomous, production-ready YouTube Shorts generator built in Python with smart API fallbacks and headless background execution._

---

<div align="center">

<!-- ── Badges ─────────────────────────────────────────────── -->
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Powered-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**🤖 Gemini AI · 🎙️ ElevenLabs + edge-tts · 🎞️ Pexels · 📺 YouTube · 💬 Telegram**

<sub>Write nothing. Publish everything. The engine writes the story, voices it, edits the film, burns the subtitles, and uploads it to YouTube — while you sleep.</sub>

</div>

---

## 📖 Table of Contents

<details open>
<summary><b>Click to expand / collapse</b></summary>

- [🎯 What Is This?](#-what-is-this)
- [✨ Key Features](#-key-features)
- [🧠 How It Works](#-how-it-works)
- [🏗️ System Architecture](#-system-architecture)
- [🔁 The Production Pipeline](#-the-production-pipeline)
- [🛡️ Smart Fallback Strategy](#-smart-fallback-strategy)
- [🔄 Job Lifecycle](#-job-lifecycle)
- [🧰 Tech Stack](#-tech-stack)
- [🚀 Getting Started](#-getting-started)
- [⚙️ Configuration Reference](#-configuration-reference)
- [🔌 API Reference](#-api-reference)
- [💬 Telegram Approval Flow](#-telegram-approval-flow)
- [🐳 Docker Deployment](#-docker-deployment)
- [📁 Project Structure](#-project-structure)
- [❓ FAQ & Troubleshooting](#-faq--troubleshooting)

</details>

---

## 🎯 What Is This?

**AutoShorts-Engine** is a fully autonomous content factory for YouTube. You give it a **topic** and a **daily quota** once — then it runs forever as a headless background server, producing and publishing complete, subtitled, narrated short-form (or long-form) videos on a schedule you define.

There is **no UI to babysit** and **no editing timeline to touch**. Every step — scripting, sourcing footage, voicing, editing, captioning, uploading — is handled by AI and code.

> 💡 **The core idea:** turn *one topic* into a *never-repeating stream* of publish-ready videos, entirely on autopilot, resilient to API quotas and server restarts.

<table>
<tr>
<td width="50%" valign="top">

**👤 What you do (once)**
1. Set a topic & language
2. Set videos-per-day & publish times
3. Add your API keys
4. Start the server

</td>
<td width="50%" valign="top">

**🤖 What the engine does (forever)**
1. Writes an original **story** with Gemini
2. Downloads matching **stock footage**
3. Generates a **voiceover**
4. Edits, resizes & **burns subtitles**
5. **Uploads** to YouTube on schedule

</td>
</tr>
</table>

---

## ✨ Key Features

| | Feature | Description |
|---|---|---|
| 🧠 | **AI Storytelling** | Gemini 2.5 Flash writes *narrative-driven* scripts (hook → climax → lesson), not dry fact lists — with per-segment footage search queries. |
| 🎙️ | **Dual-Provider TTS** | ElevenLabs premium voices with **automatic free fallback** to Microsoft `edge-tts` when quota runs out. |
| 🎞️ | **Auto Video Editing** | Fetches Pexels stock clips, trims, concatenates, and renders via MoviePy + FFmpeg. |
| 📝 | **Burned-in Subtitles** | Pixel-perfect Arabic (RTL reshaping + BiDi) & English captions, timed to the *real* audio length. |
| 📐 | **Shorts *and* Long-form** | Auto-detects format from duration: `≤180s` → **9:16 Short**, longer → **16:9 video**. |
| 📅 | **Smart Scheduling** | APScheduler distributes N videos/day across your chosen publish times, timezone-aware. |
| 🔐 | **Manual Approval Gate** | Optional Telegram bot with **Publish / Cancel** buttons before anything goes live. |
| 🧬 | **Self-Managing Memory** | The AI remembers past topics and **refuses to repeat itself**, editing its own memory each run. |
| 🛟 | **Crash Recovery** | On restart, stuck jobs are recovered and unpublished-but-ready videos are re-queued. |
| 🪶 | **Low-Resource Friendly** | Thread-capped FFmpeg — runs on a phone (Termux), a Raspberry Pi, or a tiny VPS. |
| 🔒 | **Security First** | Bearer-token auth, rate limiting, trusted-host filtering, and a `chmod 600` WAL-mode SQLite DB. |
| 🖥️ | **Headless by Design** | No frontend needed — a clean REST API + gorgeous color-coded server logs. |

---

## 🧠 How It Works

At its heart, the engine is a **FastAPI server** wrapping an **async automation pipeline** driven by a **scheduler**. Once started, it needs zero human input.

```
        ┌──────────────────────────────────────────────────────────┐
        │   You set: TOPIC · LANGUAGE · VIDEOS_PER_DAY · TIMES      │
        └──────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   ╔═══════════════════════════════════════════════════════════════════╗
   ║   AutoShorts-Engine  (headless FastAPI server, runs 24/7)          ║
   ║                                                                   ║
   ║   ⏰ 00:01 daily  ─────▶  🏭 Produce N videos  ─────▶  📅 Schedule ║
   ║                                                          uploads   ║
   ╚═══════════════════════════════════════════════════════════════════╝
                                   │
                                   ▼
              📺 Videos appear on your YouTube channel, on time.
```

Each daily cycle produces *all* of the day's videos up front, then schedules each one for upload at its designated time — so a quota hit or a slow render never derails the whole day.

---

## 🏗️ System Architecture

```mermaid
graph TD
    subgraph Client["🌐 Control Plane"]
        API["REST API<br/>(Bearer auth + rate limit)"]
        TG["💬 Telegram Bot<br/>(approval buttons)"]
    end

    subgraph Core["⚙️ Core Engine"]
        SCH["🕐 Scheduler<br/>APScheduler"]
        PIPE["🏭 Automation Pipeline"]
        DB[("🗄️ SQLite<br/>WAL · chmod 600")]
        MEM[("🧬 AI Memory<br/>ai_memory.json")]
    end

    subgraph Services["🔌 External Services"]
        AI["🧠 Gemini 2.5 Flash"]
        PX["🎞️ Pexels"]
        TTS["🎙️ ElevenLabs → edge-tts"]
        YT["📺 YouTube Data API"]
    end

    API -->|trigger / query| SCH
    SCH -->|run daily cycle| PIPE
    PIPE -->|1. script| AI
    AI <-->|read / write topics| MEM
    PIPE -->|2. footage| PX
    PIPE -->|3. voiceover| TTS
    PIPE -->|4. render + subs| FF["🎬 MoviePy + FFmpeg"]
    PIPE -->|5. upload| YT
    PIPE <-->|persist jobs| DB
    SCH -->|approval needed| TG
    TG -->|approve / cancel| SCH

    style Core fill:#1f2937,stroke:#38bdf8,color:#fff
    style Services fill:#0f766e,stroke:#5eead4,color:#fff
    style Client fill:#7c3aed,stroke:#c4b5fd,color:#fff
```

---

## 🔁 The Production Pipeline

Every single video passes through **5 deterministic steps**. If any step fails, the job is marked `failed`, temp files are cleaned, and the cycle continues with the next video.

```mermaid
sequenceDiagram
    autonumber
    participant P as 🏭 Pipeline
    participant AI as 🧠 Gemini
    participant PX as 🎞️ Pexels
    participant TTS as 🎙️ TTS
    participant FF as 🎬 FFmpeg
    participant YT as 📺 YouTube

    P->>AI: Generate story + segments (avoid past topics)
    AI-->>P: title, description, tags, script, segments[]
    P->>PX: Search & download clip per segment (concurrent)
    PX-->>P: portrait/landscape stock footage
    P->>TTS: Synthesize voiceover from script
    TTS-->>P: audio.mp3 (ElevenLabs or edge-tts)
    P->>FF: Trim + concat + resize + burn subtitles
    FF-->>P: final job_N.mp4 (9:16 or 16:9)
    Note over P: Job marked "ready" 🟢
    P->>YT: Upload at scheduled time (auto or after approval)
    YT-->>P: video_id + public URL ✅
```

<details>
<summary><b>🔍 What happens inside each step</b></summary>

<br>

| Step | Module | Action |
|:---:|---|---|
| **1** | `services/ai_service.py` | Builds a rich Arabic/English storytelling prompt (injected with **memory** of past topics), calls Gemini, cleans & repairs the JSON, validates it, and lets the AI **update its own memory**. Retries up to 3×. |
| **2** | `services/pexels_service.py` | For each segment, searches Pexels with the AI-supplied query, picks the best-resolution file matching the orientation, and downloads **concurrently** — never reusing the same clip twice. |
| **3** | `services/tts_service.py` | Tries ElevenLabs (3 model fallbacks), detects quota exhaustion, and transparently falls back to free `edge-tts`. |
| **4** | `services/video_service.py` | Resizes clips to target dimensions, concatenates, attaches audio, generates subtitles scaled to the **real** audio duration, and burns them via an FFmpeg `overlay` filter. Aggressively kills stray FFmpeg processes to avoid leaks. |
| **5** | `services/memory_service.py` | Confirms the topic is recorded so it's never repeated. |

</details>

---

## 🛡️ Smart Fallback Strategy

The engine is engineered to **keep running when things break**. This is what makes it *production-ready* rather than a demo.

```mermaid
flowchart LR
    A["🎙️ Need voiceover"] --> B{ElevenLabs<br/>configured?}
    B -->|Yes| C["Try eleven_v3"]
    C -->|fail| D["Try multilingual_v2"]
    D -->|fail| E["Try turbo_v2_5"]
    C & D & E -->|quota exceeded| F{"TTS_FALLBACK_EDGE<br/>= true?"}
    B -->|No| F
    F -->|Yes| G["✅ edge-tts (FREE)"]
    F -->|No| H["❌ Raise error"]
    E -->|success| I["✅ MP3 ready"]
    C -->|success| I
    D -->|success| I

    style G fill:#166534,stroke:#4ade80,color:#fff
    style I fill:#166534,stroke:#4ade80,color:#fff
    style H fill:#7f1d1d,stroke:#f87171,color:#fff
```

| Failure | Automatic Response |
|---|---|
| 🎙️ **ElevenLabs quota exhausted** | Silently switches to free `edge-tts` — the video still ships. |
| 📺 **YouTube daily quota exceeded** | Job is marked `quota_exceeded` and **auto-rescheduled for tomorrow** at the same time. |
| 🧠 **Gemini returns malformed JSON** | Response is cleaned, repaired, and re-requested up to **3 times**. |
| 🎞️ **A Pexels clip is missing/corrupt** | That segment is skipped; subtitles re-align to the clips that *did* download. |
| ⏱️ **FFmpeg render hangs** | Killed after `FFMPEG_TIMEOUT`; the job fails cleanly without freezing the server. |
| 💥 **Server crashes mid-render** | On restart, stuck jobs → `failed`, and `ready`-but-unpublished videos are **re-queued**. |

---

## 🔄 Job Lifecycle

Every video is a **Job** row in SQLite. Here's every state it can move through:

```mermaid
stateDiagram-v2
    [*] --> pending: created
    pending --> processing: pipeline starts
    processing --> ready: render complete 🟢
    processing --> failed: error ❌
    ready --> awaiting_approval: AUTO_PUBLISH=false
    ready --> published: AUTO_PUBLISH=true ✅
    awaiting_approval --> published: ✅ approved (Telegram/API)
    awaiting_approval --> cancelled: ❌ rejected
    ready --> quota_exceeded: YouTube quota hit
    quota_exceeded --> published: retried next day ✅
    published --> [*]
    failed --> [*]
    cancelled --> [*]
```

---

## 🧰 Tech Stack

<div align="center">

| Layer | Technology |
|---|---|
| **Web / API** | FastAPI · Uvicorn · SlowAPI (rate limiting) |
| **Scheduling** | APScheduler (cron + date triggers, timezone-aware) |
| **AI Script** | Google Generative AI — `gemini-2.5-flash` |
| **Voice** | ElevenLabs SDK · `edge-tts` (fallback) |
| **Footage** | Pexels Video API (via `httpx`) |
| **Editing** | MoviePy · FFmpeg · Pillow · `arabic-reshaper` · `python-bidi` |
| **Publishing** | Google API Python Client (YouTube Data API v3) |
| **Approval** | `python-telegram-bot` v20 |
| **Storage** | SQLModel + SQLite (WAL mode) |
| **Config / Validation** | Pydantic Settings |
| **Packaging** | Docker · docker-compose · Nginx |

</div>

---

## 🚀 Getting Started

### 📋 Prerequisites

- **Python 3.11+**
- **FFmpeg** installed and on your `PATH` &nbsp;→&nbsp; `ffmpeg -version`
- API credentials for: **Google AI Studio**, **ElevenLabs**, **Pexels**, and a **YouTube OAuth2** app

### 1️⃣ Clone & install

```bash
git clone <https://github.com/amjdcodes/> AutoShorts-Engine
cd AutoShorts-Engine

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2️⃣ Configure your environment

```bash
cp .env.example .env
```

Then open `.env` and fill in your keys (see the [Configuration Reference](#-configuration-reference) below).

### 3️⃣ Get your credentials

<details>
<summary><b>🔑 Generate a YouTube refresh token</b></summary>

<br>

After adding your `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` to `.env`:

```bash
python get_token.py
```

Open the printed link, approve access, paste back the `code`, and copy the resulting `YOUTUBE_REFRESH_TOKEN` into your `.env`.

</details>

<details>
<summary><b>🎙️ Find your ElevenLabs voice ID</b></summary>

<br>

```bash
python get_voice_id.py
```

Copy the printed ID into `ELEVENLABS_VOICE_ID` in your `.env`.

</details>

### 4️⃣ Launch the engine 🚀

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

You'll be greeted by a color-coded startup banner. The **first daily cycle kicks off automatically in the background** — the server stays responsive the whole time.

```
==============================================================
              Brambet Server — Starting Up
           YouTube Automation | Headless Mode
==============================================================
  OK  Database initialized (SQLite WAL mode, chmod 600)
  OK  Server running — Headless Mode
```

### 5️⃣ Verify it's alive

```bash
curl http://127.0.0.1:8000/health
# → {"status":"running","mode":"headless"}
```

> ⚡ **Want a video right now?** Trigger a cycle manually:
> ```bash
> curl -X POST http://127.0.0.1:8000/api/jobs/run-now \
>   -H "Authorization: Bearer YOUR_API_ACCESS_TOKEN"
> ```

---

## ⚙️ Configuration Reference

All settings live in `.env`. The most important ones:

<details open>
<summary><b>🔑 API Keys (required)</b></summary>

| Variable | Description |
|---|---|
| `GOOGLE_AI_STUDIO_API_KEY` | Gemini API key for script generation |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS key |
| `ELEVENLABS_VOICE_ID` | Voice to narrate with (see `get_voice_id.py`) |
| `PEXELS_API_KEY` | Pexels stock-video key |
| `YOUTUBE_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | YouTube OAuth2 credentials |

</details>

<details>
<summary><b>📹 Content & Scheduling</b></summary>

| Variable | Default | Description |
|---|---|---|
| `CONTENT_LANGUAGE` | `ar` | `ar` (Arabic) or `en` (English) |
| `VIDEO_TOPIC` | — | The subject the AI writes about |
| `VIDEO_DURATION_SECONDS` | `60` | Target video length |
| `SHORT_MAX_DURATION_SECONDS` | `180` | `≤` this → Short (9:16); longer → 16:9 |
| `VIDEOS_PER_DAY` | `1` | How many videos to produce daily |
| `PUBLISH_TIMES` | — | e.g. `08:00,14:00,20:00` (blank = auto 08:00–22:00) |
| `AUTO_PUBLISH` | `false` | `true` = publish automatically · `false` = require approval |
| `TIMEZONE` | `UTC` | IANA name, e.g. `Africa/Cairo`, `Asia/Riyadh` |

</details>

<details>
<summary><b>🎙️ TTS Fallback</b></summary>

| Variable | Default | Description |
|---|---|---|
| `TTS_FALLBACK_EDGE` | `true` | Fall back to free edge-tts on ElevenLabs quota |
| `EDGE_TTS_VOICE` | *(auto)* | e.g. `ar-SA-HamedNeural`, `en-US-EmmaMultilingualNeural` |

</details>

<details>
<summary><b>🎨 Subtitles & 🎥 Rendering Performance</b></summary>

| Variable | Default | Description |
|---|---|---|
| `SUBTITLE_ENABLED` | `true` | Burn captions into the video |
| `SUBTITLE_FONT_SIZE` | `42` | Caption size in px |
| `SUBTITLE_COLOR` | `#FFFFFF` | Text color |
| `SUBTITLE_BG_OPACITY` | `0.6` | Background band opacity |
| `FFMPEG_THREADS` | `2` | **Cap CPU** — set to `2` on phones/weak VPS |
| `FFMPEG_PRESET` | `fast` | `ultrafast`→`slower` (speed vs quality) |
| `FFMPEG_TIMEOUT` | `900` | Max seconds per render before kill |

> ⚠️ On an 8-core device, FFmpeg defaults to using **all cores (800% CPU)** and can freeze the system. `FFMPEG_THREADS=2` is your safety valve.

</details>

<details>
<summary><b>🔐 Security & Server</b></summary>

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random 32+ char secret — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `API_ACCESS_TOKEN` | Bearer token required by every API call |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `HOST` / `PORT` | Bind address (default `127.0.0.1:8000`) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional — enables the approval bot |

</details>

---

## 🔌 API Reference

> 🔒 Every endpoint (except `/health`) requires the header:
> `Authorization: Bearer <API_ACCESS_TOKEN>`

<details open>
<summary><b>🎬 Jobs — <code>/api/jobs</code></b></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/jobs/` | List jobs (filter by `status`, `date_from`, `date_to`) |
| `GET` | `/api/jobs/{id}` | Get one job's full details |
| `POST` | `/api/jobs/run-now` | 🚀 Trigger a daily cycle immediately |
| `PUT` | `/api/jobs/{id}/approve` | ✅ Approve an `awaiting_approval` job |
| `PUT` | `/api/jobs/{id}/cancel` | ❌ Cancel a job |
| `DELETE` | `/api/jobs/{id}` | 🗑️ Delete a job + its media files |

</details>

<details>
<summary><b>📊 Stats — <code>/api/stats</code></b></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stats/` | Totals, success rate, today's count, last published |
| `GET` | `/api/stats/scheduler` | Scheduler status + upcoming scheduled uploads |

</details>

<details>
<summary><b>🧬 Memory — <code>/api/memory</code></b></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/memory/` | Full AI memory (topics + guidelines) |
| `GET` | `/api/memory/topics` | Covered topics (won't be repeated) |
| `POST` | `/api/memory/topics` | Manually add a topic |
| `DELETE` | `/api/memory/topics` | Remove a topic (by name or index) |
| `GET` · `POST` · `DELETE` | `/api/memory/guidelines` | Manage AI writing guidelines |
| `DELETE` | `/api/memory/` | 🧹 Wipe all memory |

</details>

**Example — check your stats:**

```bash
curl http://127.0.0.1:8000/api/stats/ \
  -H "Authorization: Bearer YOUR_API_ACCESS_TOKEN"
```

```json
{
  "total_jobs": 42,
  "published": 38,
  "failed": 2,
  "today_published": 5,
  "success_rate": 90.5,
  "last_published": { "title": "...", "youtube_url": "https://youtube.com/shorts/..." }
}
```

---

## 💬 Telegram Approval Flow

When `AUTO_PUBLISH=false` and a Telegram bot is configured, every finished video waits for your tap:

```
┌─────────────────────────────────────────┐
│  🎬 New Video Ready for Publishing       │
│                                         │
│  📌 Title:    The Secret of the Nile    │
│  📝 Desc:     Imagine standing where... │
│  🏷️ Tags:     history, egypt, mystery   │
│  ⏱️ Duration: 60 seconds                │
│  📹 Type:     Short (9:16)              │
│                                         │
│   [ ✅ Publish Now ]   [ ❌ Cancel ]     │
└─────────────────────────────────────────┘
```

Tap **Publish Now** → it uploads instantly. Tap **Cancel** → the job is dropped. No dashboard required.

---

## 🐳 Docker Deployment

The project ships production-ready with FFmpeg, Noto fonts, a non-root user, and resource limits baked in.

```bash
# 1. Fill in your .env, then:
docker compose up -d --build

# 2. Watch the logs
docker compose logs -f brambet
```

The `docker-compose.yml` includes an **Nginx** reverse-proxy service (add your `nginx.conf` + TLS certs) and caps the engine at **2 CPUs / 4 GB RAM** so it plays nicely on shared hosts.

<details>
<summary><b>What the Docker image does for you</b></summary>

- Installs `ffmpeg` + `fonts-noto` system-wide
- Auto-downloads the Arabic & English subtitle fonts
- Runs as an unprivileged `brambet` user
- Persists `temp/`, `output/`, and `brambet.db` via volumes
- `restart: unless-stopped` for true 24/7 operation

</details>

---

## 📁 Project Structure

```
AutoShorts-Engine/
├── app/
│   ├── main.py              # 🚪 FastAPI app + lifespan startup/recovery
│   ├── config.py            # ⚙️ Pydantic settings (from .env)
│   ├── scheduler.py         # 🕐 Daily cycle, pipeline orchestration, retries
│   ├── models.py            # 🗄️ Job model (SQLModel)
│   ├── database.py          # 💾 SQLite engine (WAL, migrations, chmod 600)
│   ├── security.py          # 🔐 Bearer-token auth
│   ├── limiter.py           # 🚦 Rate limiting
│   ├── logger_util.py       # 🎨 Color-coded pro logging
│   ├── telegram_bot.py      # 💬 Approval bot
│   ├── routers/             # 🔌 jobs · stats · memory endpoints
│   └── services/
│       ├── ai_service.py        # 🧠 Gemini script generation
│       ├── pexels_service.py    # 🎞️ Stock footage
│       ├── tts_service.py       # 🎙️ ElevenLabs → edge-tts
│       ├── video_service.py     # 🎬 MoviePy + FFmpeg render
│       ├── subtitle_service.py  # 📝 Arabic/English caption rendering
│       ├── memory_service.py    # 🧬 Anti-repetition memory
│       └── youtube_service.py   # 📺 Upload + quota handling
├── assets/fonts/            # 🔤 Noto Sans (Arabic + Latin)
├── get_token.py             # 🔑 YouTube OAuth helper
├── get_voice_id.py          # 🎙️ ElevenLabs voice helper
├── Dockerfile · docker-compose.yml
├── requirements.txt · pyproject.toml
└── .env.example
```

---

## ❓ FAQ & Troubleshooting

<details>
<summary><b>The server won't start — "Missing required env vars"</b></summary>

<br>Fill in <b>all</b> required keys in <code>.env</code>: <code>GOOGLE_AI_STUDIO_API_KEY</code>, <code>ELEVENLABS_API_KEY</code>, <code>PEXELS_API_KEY</code>, <code>YOUTUBE_CLIENT_ID</code>, <code>SECRET_KEY</code>, <code>API_ACCESS_TOKEN</code>. The engine refuses to boot without them — by design.

</details>

<details>
<summary><b>My phone/VPS freezes during rendering</b></summary>

<br>Set <code>FFMPEG_THREADS=2</code> and <code>FFMPEG_PRESET=ultrafast</code>. FFmpeg otherwise grabs every CPU core.

</details>

<details>
<summary><b>Videos are made but never uploaded</b></summary>

<br>Check <code>AUTO_PUBLISH</code>. If it's <code>false</code>, videos sit in <code>awaiting_approval</code> until you approve them via Telegram or <code>PUT /api/jobs/{id}/approve</code>.

</details>

<details>
<summary><b>"409 Conflict" spam from Telegram</b></summary>

<br>Another process is still polling the same bot token. Kill it before restarting — only one poller per token is allowed.

</details>

<details>
<summary><b>YouTube uploads stopped with "quota_exceeded"</b></summary>

<br>Nothing to do — the engine <b>auto-reschedules</b> the job for the same time tomorrow, when your daily YouTube quota resets.

</details>

---

<div align="center">

### ⭐ Set the topic. Start the server. Walk away.

**AutoShorts-Engine keeps creating — long after you've closed the terminal.**

<sub>Built with Python, FastAPI & FFmpeg · Runs anywhere from a Raspberry Pi to the cloud</sub>

</div>
