from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ...core.session_manager import get_manager
from ...core.config import config

router = APIRouter()


class StartMeetingRequest(BaseModel):
    title: str
    platform: str = "gmeet"
    attendees: List[str] = []
    calendar_event_id: Optional[str] = None
    joined_late: bool = False


class FeedbackRequest(BaseModel):
    text: str
    weight: float = 1.0


@router.get("/meetings/today")
async def get_today_meetings():
    try:
        from ...integrations.calendar_sync import CalendarSync
        cal = CalendarSync()
        events = cal.get_today_events()
        return [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "attendees": e.attendees,
                "platform": e.platform,
                "meet_link": e.meet_link,
                "description": e.description[:300] if e.description else "",
            }
            for e in events
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meetings/status")
async def get_status():
    sm = get_manager()
    session = sm.session
    return {
        "status": sm.status,
        "active": bool(session and session.is_active),
        "meeting_id": session.id if session else None,
        "title": session.title if session else None,
        "start_time": session.start_time.isoformat() if session else None,
        "transcript_count": len(session.transcript) if session else 0,
        "trigger_count": len(session.trigger_events) if session else 0,
    }


@router.post("/meetings/start")
async def start_meeting(req: StartMeetingRequest):
    sm = get_manager()
    session = await sm.start_meeting(
        title=req.title,
        platform=req.platform,
        attendees=req.attendees,
        calendar_event_id=req.calendar_event_id,
        joined_late=req.joined_late,
    )
    return {
        "meeting_id": session.id,
        "title": session.title,
        "start_time": session.start_time.isoformat(),
    }


@router.post("/meetings/stop")
async def stop_meeting():
    sm = get_manager()
    if not sm.session or not sm.session.is_active:
        raise HTTPException(status_code=400, detail="No active meeting")
    summary = await sm.stop_meeting()
    if not summary:
        return {"ok": True}
    return {
        "meeting_id": summary.meeting_id,
        "title": summary.title,
        "summary": summary.summary,
        "key_decisions": summary.key_decisions,
        "action_items": summary.action_items,
        "my_action_items": summary.my_action_items,
        "duration_minutes": summary.duration_minutes,
        "notion_url": summary.notion_url,
    }


@router.post("/meetings/catchup")
async def request_catchup():
    sm = get_manager()
    if not sm.session or not sm.session.is_active:
        raise HTTPException(status_code=400, detail="No active meeting")
    catchup = await sm.request_catchup()
    return {"catchup": catchup}


@router.get("/meetings/history")
async def get_history():
    transcripts_dir = Path(config.TRANSCRIPTS_DIR)
    if not transcripts_dir.exists():
        return []
    files = sorted(transcripts_dir.glob("*.json"), reverse=True)[:20]
    results = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
            results.append({
                "id": data.get("id"),
                "title": data.get("title"),
                "start": data.get("start"),
                "end": data.get("end"),
                "attendees": data.get("attendees", []),
                "transcript_lines": len(data.get("transcript", [])),
            })
        except Exception:
            pass
    return results


@router.post("/meetings/feedback")
async def add_feedback(req: FeedbackRequest):
    sm = get_manager()
    sm.context_store.add_preference(req.text, req.weight)
    return {"ok": True}


@router.get("/whatsapp/status")
async def whatsapp_status():
    sm = get_manager()
    status = await sm.notifier.check_whatsapp_status()
    return {"status": status}
