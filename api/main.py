from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .routes import meetings, files, feedback

BASE_DIR = Path(__file__).parent.parent

app = FastAPI(title="Copilot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup():
    from ..core.session_manager import get_manager
    sm = get_manager()

    async def on_transcript(chunk):
        await manager.broadcast({
            "type": "transcript",
            "speaker": chunk.speaker,
            "text": chunk.text,
            "timestamp": chunk.timestamp,
        })

    async def on_event(event):
        await manager.broadcast({
            "type": "trigger",
            "question": event.question,
            "speaker": event.speaker,
            "suggestion": event.suggestion,
            "confidence": event.confidence,
            "context": event.context[:3],
            "timestamp": event.timestamp,
        })

    sm.register_transcript_callback(on_transcript)
    sm.register_event_callback(on_event)

    # Wire Notion into session manager's stop_meeting
    _wire_notion(sm)
    # Schedule pre-meeting briefs
    asyncio.create_task(_brief_scheduler(sm))


def _wire_notion(sm):
    """Patch session_manager.stop_meeting to also create Notion pages."""
    original_stop = sm.stop_meeting

    async def stop_with_notion():
        summary = await original_stop()
        if summary:
            try:
                from ..integrations.notion_sync import NotionSync
                notion = NotionSync()
                url = notion.create_meeting_page(summary)
                summary.notion_url = url
                await sm.notifier._send_whatsapp(
                    sm.notifier.__class__  # noop if no phone
                    .__module__,  # just trigger, real send already in stop_meeting
                    "",
                ) if False else None
            except Exception as e:
                print(f"[Notion] Failed: {e}")
        return summary

    sm.stop_meeting = stop_with_notion


async def _brief_scheduler(sm):
    """Send a pre-meeting brief 5 minutes before each calendar event."""
    from ..core.config import config
    while True:
        try:
            from ..integrations.calendar_sync import CalendarSync
            from datetime import datetime, timezone, timedelta
            cal = CalendarSync()
            events = cal.get_events_in_range(minutes_from_now=4, hours=0.5 / 60 * 10)
            for event in events:
                now = datetime.now(timezone.utc)
                starts_in = int((event.start - now).total_seconds() / 60)
                if 4 <= starts_in <= 6:
                    context = sm.context_store.search(event.title, n_results=5)
                    brief = sm.summarizer.pre_meeting_brief(
                        event.title, event.attendees, event.description, context
                    )
                    await sm.notifier.send_pre_brief(event.title, brief, starts_in)
        except Exception as e:
            pass
        await asyncio.sleep(60)


# Serve dashboard
@app.get("/")
async def dashboard():
    return FileResponse(BASE_DIR / "dashboard" / "index.html")


dashboard_static = BASE_DIR / "dashboard" / "static"
if dashboard_static.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_static)), name="static")
