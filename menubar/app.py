from __future__ import annotations
"""
Copilot macOS menubar app.
Run this as the entry point — it starts the FastAPI server in a background
thread and takes over the main thread for the rumps menubar.
"""
import rumps
import threading
import subprocess
import sys
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

rumps.debug_mode(False)


def start_whatsapp_bridge():
    """Start the Node.js WhatsApp bridge in background."""
    try:
        subprocess.Popen(
            ["node", "integrations/whatsapp_bridge.js"],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("[Menubar] node not found — WhatsApp bridge not started")


def start_api_server():
    """Start FastAPI in a daemon thread."""
    import uvicorn
    sys.path.insert(0, str(BASE_DIR))
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="error",
    )


class CopilotApp(rumps.App):
    def __init__(self):
        super().__init__(
            "Copilot",
            icon=None,
            title="🎙",
            quit_button="Quit Copilot",
        )
        self.menu = [
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            rumps.MenuItem("Start Listening", callback=self.toggle_listening),
            None,  # separator
            rumps.MenuItem("Scan WhatsApp QR", callback=self.open_qr),
            None,
        ]
        self._listening = False
        self._poll_timer = rumps.Timer(self._poll_status, 5)
        self._poll_timer.start()

    def open_dashboard(self, _):
        webbrowser.open("http://localhost:8000")

    def open_qr(self, _):
        webbrowser.open("http://localhost:3001/qr-web")

    def toggle_listening(self, sender):
        import httpx
        if not self._listening:
            try:
                r = httpx.post(
                    "http://localhost:8000/api/meetings/start",
                    json={"title": "Manual Meeting", "platform": "gmeet"},
                    timeout=5,
                )
                r.raise_for_status()
                self._listening = True
                sender.title = "Stop Listening"
                self.title = "🔴"
                rumps.notification("Copilot", "Listening started", "Monitoring for triggers")
            except Exception as e:
                rumps.notification("Copilot", "Error", str(e))
        else:
            try:
                r = httpx.post("http://localhost:8000/api/meetings/stop", timeout=10)
                r.raise_for_status()
                self._listening = False
                sender.title = "Start Listening"
                self.title = "🎙"
                rumps.notification("Copilot", "Meeting ended", "Summary sent to WhatsApp")
            except Exception as e:
                rumps.notification("Copilot", "Error", str(e))

    def _poll_status(self, _):
        import httpx
        try:
            r = httpx.get("http://localhost:8000/api/meetings/status", timeout=2)
            data = r.json()
            if data.get("active"):
                self.title = "🔴"
                self._listening = True
            elif data.get("status") == "processing":
                self.title = "⏳"
            else:
                if self._listening:
                    self._listening = False
                self.title = "🎙"
        except Exception:
            self.title = "⚫"


def main():
    # Start WhatsApp bridge
    start_whatsapp_bridge()

    # Start FastAPI in background thread
    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(2)  # give server a moment to start

    # Run menubar on main thread (macOS requirement)
    CopilotApp().run()


if __name__ == "__main__":
    main()
