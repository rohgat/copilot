from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class TranscriptChunk:
    meeting_id: str
    speaker: str
    text: str
    timestamp: float
    start: float = 0.0
    end: float = 0.0


@dataclass
class TriggerEvent:
    meeting_id: str
    question: str
    speaker: str
    context: List[str]
    suggestion: str
    confidence: float
    timestamp: float


@dataclass
class AttendeeProfile:
    name: str
    email: str = ""
    role: str = ""
    meetings_together: int = 0
    topics: List[str] = field(default_factory=list)
    last_seen: Optional[datetime] = None


@dataclass
class MeetingSession:
    id: str
    title: str
    start_time: datetime
    platform: str
    attendees: List[str] = field(default_factory=list)
    transcript: List[TranscriptChunk] = field(default_factory=list)
    trigger_events: List[TriggerEvent] = field(default_factory=list)
    is_active: bool = True
    joined_late: bool = False
    late_join_index: int = 0
    end_time: Optional[datetime] = None
    calendar_event_id: Optional[str] = None
    notion_page_id: Optional[str] = None
    notion_url: Optional[str] = None
    pre_meeting_files: List[str] = field(default_factory=list)

    def full_transcript_text(self) -> str:
        return "\n".join(f"{c.speaker}: {c.text}" for c in self.transcript)

    def transcript_since_join(self) -> str:
        chunks = self.transcript[self.late_join_index:]
        return "\n".join(f"{c.speaker}: {c.text}" for c in chunks)

    def transcript_before_join(self) -> str:
        chunks = self.transcript[: self.late_join_index]
        return "\n".join(f"{c.speaker}: {c.text}" for c in chunks)

    def duration_minutes(self) -> int:
        end = self.end_time or datetime.now()
        return int((end - self.start_time).total_seconds() / 60)


@dataclass
class MeetingSummary:
    meeting_id: str
    title: str
    summary: str
    key_decisions: List[str]
    action_items: List[str]
    my_action_items: List[str]
    catchup_summary: Optional[str] = None
    transcript_path: Optional[str] = None
    notion_url: Optional[str] = None
    duration_minutes: int = 0
    attendees: List[str] = field(default_factory=list)
    date: Optional[datetime] = None


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: List[str] = field(default_factory=list)
    description: str = ""
    meet_link: Optional[str] = None
    zoom_link: Optional[str] = None
    platform: str = "unknown"
