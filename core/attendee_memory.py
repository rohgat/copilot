from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from .models import MeetingSession, AttendeeProfile
from .config import config


class AttendeeMemory:
    """Builds lightweight profiles per attendee from meeting history."""

    def __init__(self):
        self._profiles: Dict[str, AttendeeProfile] = {}
        self._path = Path(config.PREFS_PATH).parent / "attendees.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path) as f:
                    raw = json.load(f)
                for name, data in raw.items():
                    last = data.get("last_seen")
                    self._profiles[name] = AttendeeProfile(
                        name=name,
                        email=data.get("email", ""),
                        role=data.get("role", ""),
                        meetings_together=data.get("meetings_together", 0),
                        topics=data.get("topics", []),
                        last_seen=datetime.fromisoformat(last) if last else None,
                    )
            except Exception:
                pass

    def _save(self):
        raw = {}
        for name, p in self._profiles.items():
            raw[name] = {
                "email": p.email,
                "role": p.role,
                "meetings_together": p.meetings_together,
                "topics": p.topics[-20:],
                "last_seen": p.last_seen.isoformat() if p.last_seen else None,
            }
        with open(self._path, "w") as f:
            json.dump(raw, f, indent=2)

    def update_from_session(self, session: MeetingSession):
        """Update attendee profiles after a meeting ends."""
        transcript = session.full_transcript_text()
        for attendee in session.attendees:
            p = self._profiles.setdefault(
                attendee, AttendeeProfile(name=attendee)
            )
            p.meetings_together += 1
            p.last_seen = session.end_time or datetime.now()
        self._save()

    def get_context(self, attendees: List[str]) -> str:
        """Return a concise context string for the given attendees."""
        lines = []
        for name in attendees:
            p = self._profiles.get(name)
            if not p or p.meetings_together == 0:
                continue
            last = p.last_seen.strftime("%b %d") if p.last_seen else "unknown"
            lines.append(
                f"• {name}: {p.meetings_together} meetings together, last on {last}"
                + (f" · Role: {p.role}" if p.role else "")
            )
        return "\n".join(lines) if lines else "No prior meeting history with these attendees."

    def get_profile(self, name: str) -> Optional[AttendeeProfile]:
        return self._profiles.get(name)
