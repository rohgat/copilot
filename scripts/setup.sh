#!/bin/bash
set -e

echo "══════════════════════════════════"
echo "  Copilot — One-time Setup"
echo "══════════════════════════════════"
cd "$(dirname "$0")/.."

# 1. Homebrew check
if ! command -v brew &>/dev/null; then
  echo "❌ Homebrew not found. Install from https://brew.sh"
  exit 1
fi
echo "✅ Homebrew found"

# 2. Python 3.12
if ! command -v python3.12 &>/dev/null; then
  echo "📦 Installing Python 3.12..."
  brew install python@3.12
fi
echo "✅ Python 3.12: $(python3.12 --version)"

# 3. BlackHole
if ! system_profiler SPAudioDataType 2>/dev/null | grep -q "BlackHole"; then
  echo ""
  echo "⚠️  BlackHole 2ch not detected."
  echo "    Install it: brew install --cask blackhole-2ch"
  echo "    Then set up Multi-Output Device in Audio MIDI Setup."
  echo "    See README.md → Audio Setup for step-by-step instructions."
  echo ""
fi

# 4. Python venv
if [ ! -d ".venv" ]; then
  echo "📦 Creating Python virtual environment..."
  python3.12 -m venv .venv
fi

echo "📦 Installing Python dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "✅ Python dependencies installed"

# 5. Node + npm packages
if ! command -v node &>/dev/null; then
  echo "📦 Installing Node.js..."
  brew install node
fi
echo "✅ Node.js: $(node --version)"

echo "📦 Installing Node dependencies..."
npm install --silent
echo "✅ Node dependencies installed"

# 6. .env
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "📝 Created .env — fill in your API keys:"
  echo "   ANTHROPIC_API_KEY  → console.anthropic.com"
  echo "   NOTION_TOKEN       → notion.so/my-integrations"
  echo "   USER_PHONE         → your number in +91xxxxxxxxxx format"
  echo "   USER_NAME          → your first name (used for detection)"
  echo ""
else
  echo "✅ .env exists"
fi

# 7. Google credentials reminder
if [ ! -f "google_credentials.json" ]; then
  echo ""
  echo "📝 Google Calendar setup needed:"
  echo "   1. Go to console.cloud.google.com"
  echo "   2. Create a project → Enable Google Calendar API"
  echo "   3. Create OAuth 2.0 Desktop credentials"
  echo "   4. Download as google_credentials.json into this folder"
  echo "   (First run will open a browser for OAuth consent)"
  echo ""
fi

echo ""
echo "══════════════════════════════════"
echo "  Setup complete. Run: ./scripts/start.sh"
echo "══════════════════════════════════"
