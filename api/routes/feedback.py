from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from ...core.session_manager import get_manager

router = APIRouter()


class StarRequest(BaseModel):
    bullets: List[str]
    weight: float = 1.0


class FlagRequest(BaseModel):
    text: str
    false_positive: bool = False


@router.post("/feedback/star")
async def star_bullets(req: StarRequest):
    """User starred important bullets from a meeting summary."""
    sm = get_manager()
    for bullet in req.bullets:
        sm.context_store.add_preference(bullet.strip(), req.weight)
    return {"ok": True, "starred": len(req.bullets)}


@router.post("/feedback/flag")
async def flag_trigger(req: FlagRequest):
    """User flagged a trigger as false positive (irrelevant) or missed trigger."""
    sm = get_manager()
    if req.false_positive:
        # Negative signal: slightly reduce weight for this type of content
        sm.context_store.add_preference(req.text.strip(), -0.5)
    else:
        # Missed trigger: add as positive preference
        sm.context_store.add_preference(req.text.strip(), 1.5)
    return {"ok": True}


@router.get("/feedback/weekly-digest")
async def weekly_digest():
    """Generate and send this week's digest."""
    import json
    from pathlib import Path
    from ...core.config import config
    from ...core.models import MeetingSummary
    from ...core.summarizer import Summarizer
    from ...core.notifier import Notifier
    from datetime import datetime, timedelta

    transcripts_dir = Path(config.TRANSCRIPTS_DIR)
    if not transcripts_dir.exists():
        return {"ok": True, "message": "No meetings recorded yet"}

    summaries = []
    week_ago = datetime.now() - timedelta(days=7)

    for f in sorted(transcripts_dir.glob("*.json"), reverse=True)[:20]:
        try:
            with open(f) as fp:
                data = json.load(fp)
            start = datetime.fromisoformat(data.get("start", ""))
            if start < week_ago:
                continue
            summaries.append(
                MeetingSummary(
                    meeting_id=data.get("id", ""),
                    title=data.get("title", "Unknown"),
                    summary="",
                    key_decisions=[],
                    action_items=[],
                    my_action_items=[],
                    date=start,
                    attendees=data.get("attendees", []),
                )
            )
        except Exception:
            pass

    if not summaries:
        return {"ok": True, "message": "No meetings this week"}

    summarizer = Summarizer()
    notifier = Notifier()
    digest = summarizer.weekly_digest(summaries)
    await notifier.send_weekly_digest(digest)
    return {"ok": True, "meetings_included": len(summaries), "digest": digest}
