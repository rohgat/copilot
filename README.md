# Copilot — AI Meeting Assistant

Real-time AI layer for every call. Detects when you're addressed, retrieves context from past meetings, and delivers a full summary with action items the moment each meeting ends.

**Stage 1:** Available mode — you're on the call, Copilot listens and nudges you.

---

## What it does

- **Name detection** — Claude monitors the live transcript and alerts you the moment someone asks you a question
- **Instant context** — retrieves relevant snippets from past meetings and uploaded docs to help you answer
- **Mid-call catch-up** — joined late? One tap summarises everything that happened before you joined
- **End-of-meeting summary** — automatic summary, key decisions, and your action items sent to WhatsApp + Notion
- **Preference learning** — star important bullets; the model re-ranks context around your interests over time
- **Weekly digest** — Sunday summary of open action items and recurring topics
- **Pre-meeting brief** — 5 minutes before each calendar meeting, get a WhatsApp brief on who's attending and what was discussed last time

---

## Requirements

- macOS (Apple Silicon M-series)
- [BlackHole 2ch](https://existentialcrisis.com/blackhole) — virtual audio driver
- [Ollama](https://ollama.com) — local LLM runner (no API key, runs on-device)
- Notion integration token
- Google Calendar OAuth credentials
- WhatsApp personal number

---

## Setup

### 1. Run the setup script

```bash
cd ~/copilot
chmod +x scripts/setup.sh scripts/start.sh
./scripts/setup.sh
```

This installs Python 3.12, Node.js, all dependencies, and creates your `.env`.

### 2. Fill in `.env`

```
USER_NAME=Rohit
USER_PHONE=+919xxxxxxxxx
NOTION_TOKEN=ntn_...
```

Get your Notion token at [notion.so/my-integrations](https://www.notion.so/my-integrations) → New integration → copy token → share your workspace page with the integration.

> **LLM runs locally via Ollama** — no API key needed. The setup script installs Ollama and pulls `llama3.1:8b` (~5 GB, one-time download). Swap to `qwen2.5:14b` in `.env` for better quality if you have the RAM.

### 3. Audio setup (BlackHole)

Install BlackHole:
```bash
brew install --cask blackhole-2ch
```

Create a Multi-Output Device in **Audio MIDI Setup** (open with Spotlight):
1. Click `+` → Create Multi-Output Device
2. Check: **BlackHole 2ch** + your speakers/headphones
3. Set this Multi-Output Device as your system output in System Settings → Sound

This lets Copilot hear your meetings while you still hear audio normally.

### 4. Google Calendar

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → **APIs & Services** → Enable **Google Calendar API**
3. **Credentials** → Create Credentials → **OAuth 2.0 Client ID** → Desktop app
4. Download JSON → rename to `google_credentials.json` → place in `~/copilot/`

First run will open a browser for consent — sign in once and it stores a token.

### 5. Notion workspace

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create a new integration named "Copilot"
3. Copy the Internal Integration Token → paste as `NOTION_TOKEN` in `.env`
4. Create a new page in Notion (e.g. "Copilot Meeting Notes") → click `···` → Add connections → Copilot
5. On first run, the database is created automatically inside that page

---

## Running

```bash
./scripts/start.sh
```

A 🎙 icon appears in your menubar. Open the dashboard at [localhost:8000](http://localhost:8000).

**First run:** Open [localhost:3001/qr-web](http://localhost:3001/qr-web) and scan the QR code with your WhatsApp to link your number. This is a one-time step.

---

## Using Copilot

1. **Before a meeting** — open the dashboard, find the meeting in the sidebar, optionally upload pre-meeting docs (agenda, deck)
2. **Join your meeting** in Google Meet or Zoom as normal
3. **Click "Start Copilot"** on the meeting card (or the menubar icon)
4. **Copilot listens** — when your name is mentioned + a question is asked, you get a macOS notification + WhatsApp message with context and a suggested response
5. **Joined late?** Click **Catch-up** in the dashboard for an instant brief on what you missed
6. **End the meeting** — click Stop (or Copilot auto-detects silence). Summary goes to WhatsApp + Notion
7. **Review the summary** in Notion, star ⭐ important bullets — the model learns your priorities

---

## Feedback loop

The more you use Copilot, the better it gets:
- ⭐ **Star** a notification or summary bullet → that topic gets higher weight in future context retrieval
- ✕ **Flag** an irrelevant trigger → reduces false positives for similar phrasing
- Each meeting's transcript is embedded and searchable by future meetings

---

## Weekly digest

Send yourself this week's digest manually from the dashboard, or schedule a Sunday cron:

```bash
curl -X GET http://localhost:8000/api/feedback/weekly-digest
```

---

## Project structure

```
copilot/
├── core/                   Python pipeline
│   ├── audio.py            BlackHole audio capture
│   ├── transcriber.py      faster-whisper STT
│   ├── detector.py         Claude name/intent detection
│   ├── context.py          ChromaDB vector store
│   ├── summarizer.py       Meeting summary + catch-up + suggestion
│   ├── notifier.py         macOS + WhatsApp notifications
│   ├── silence.py          Auto-end on sustained silence
│   ├── attendee_memory.py  Per-attendee profile builder
│   └── session_manager.py  Central coordinator
├── integrations/
│   ├── calendar_sync.py    Google Calendar
│   ├── notion_sync.py      Notion page creation
│   └── whatsapp_bridge.js  Node.js WhatsApp service
├── api/                    FastAPI backend
├── dashboard/              Local web UI (localhost:8000)
├── menubar/                macOS menubar app (rumps)
└── scripts/                Setup + start scripts
```

---

## Stage 2 (planned)

- Unavailable mode — bot joins meetings on your behalf via Playwright
- Voice response — Kokoro TTS speaks your answers in the meeting
- Voice cloning — responses in your voice
- Availability toggle from Google Calendar
