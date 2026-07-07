#!/bin/bash
cd "$(dirname "$0")/.."

# Activate venv
source .venv/bin/activate 2>/dev/null || {
  echo "❌ venv not found. Run ./scripts/setup.sh first."
  exit 1
}

# Check .env
if [ ! -f ".env" ]; then
  echo "❌ .env not found. Run ./scripts/setup.sh first."
  exit 1
fi

echo "🎙  Starting Copilot..."
echo "   Dashboard → http://localhost:8000"
echo "   WhatsApp  → http://localhost:3001/qr-web (first run only)"
echo ""

# Run menubar app (this also starts FastAPI + WhatsApp bridge internally)
python3 -m menubar.app
