from __future__ import annotations
import asyncio
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable
from .models import MeetingSession, MeetingSummary, TriggerEvent, TranscriptChunk
from .audio import AudioCapture
from .transcriber import Transcriber
from .detector import Detector
from .context import ContextStore
from .summarizer import Summarizer
from .notifier import Notifier
from .silence import SilenceDetector
from .attendee_memory import AttendeeMemory
from .config import config


class SessionManager:
    """Central coordinator for all meeting components."""

    def __init__(self):
        self.session: Optional[MeetingSession] = None
        self.audio = AudioCapture()
        self.transcriber = Transcriber()
        self.detector = Detector()
        self.context_store = ContextStore()
        self.summarizer = Summarizer()
        self.notifier = Notifier()
        self.silence = SilenceDetector()
        self.attendee_memory = AttendeeMemory()

        self._tasks: List[asyncio.Task] = []
        self._transcript_callbacks: List[Callable] = []
        self._event_callbacks: List[Callable] = []
        self._status: str = "idle"  # idle | listening | processing

    @property
    def status(self) -> str:
        return self._status

    def register_transcript_callback(self, fn: Callable):
        self._transcript_callbacks.append(fn)

    def register_event_callback(self, fn: Callable):
        self._event_callbacks.append(fn)

    async def start_meeting(
        self,
        title: str,
        platform: str = "gmeet",
        attendees: Optional[List[str]] = None,
        calendar_event_id: Optional[str] = None,
        joined_late: bool = False,
    ) -> MeetingSession:
        if self.session and self.session.is_active:
            await self.stop_meeting()

        meeting_id = str(uuid.uuid4())[:8]
        self.session = MeetingSession(
            id=meeting_id,
            title=title,
            start_time=datetime.now(),
            platform=platform,
            attendees=attendees or [],
            joined_late=joined_late,
            calendar_event_id=calendar_event_id,
        )

        await self.audio.start()
        await self.transcriber.start(self.audio, meeting_id)
        await self.detector.start(self.transcriber, meeting_id)
        await self.silence.start(self.audio, self._on_silence_end)

        self._tasks = [
            asyncio.create_task(self._transcript_loop()),
            asyncio.create_task(self._event_loop()),
        ]

        self._status = "listening"
        print(f"[Copilot] Meeting started: {title} ({meeting_id})")
        return self.session

    async def stop_meeting(self) -> Optional[MeetingSummary]:
        if not self.session or not self.session.is_active:
            return None

        self._status = "processing"
        self.session.is_active = False
        self.session.end_time = datetime.now()

        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        await self.silence.stop()
        await self.transcriber.stop()
        await self.audio.stop()
        await self.detector.stop()

        summary = await asyncio.get_running_loop().run_in_executor(
            None, self.summarizer.end_of_meeting, self.session
        )

        self._save_transcript(self.session)
        self.context_store.add_meeting_summary(
            self.session.id,
            summary.summary,
            summary.title,
            self.session.start_time.isoformat(),
        )
        self.attendee_memory.update_from_session(self.session)

        await self.notifier.send_summary(summary)

        self._status = "idle"
        return summary

    async def request_catchup(self) -> str:
        """Mark late join point and generate a catch-up summary."""
        if not self.session:
            return "No active meeting."
        self.session.joined_late = True
        self.session.late_join_index = len(self.session.transcript)
        loop = asyncio.get_running_loop()
        catchup = await loop.run_in_executor(
            None, self.summarizer.mid_call_catchup, self.session
        )
        await self.notifier.send_catchup(self.session.title, catchup)
        return catchup

    async def _transcript_loop(self):
        while True:
            try:
                chunk: TranscriptChunk = await self.transcriber.get_chunk()
                if self.session:
                    self.session.transcript.append(chunk)
                    self.context_store.add_transcript_chunk(chunk)
                    for cb in self._transcript_callbacks:
                        try:
                            await cb(chunk)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SessionManager] Transcript loop error: {e}")

    async def _event_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                event: TriggerEvent = await self.detector.get_event()
                if not self.session:
                    continue

                self._status = "processing"
                context = self.context_store.search(event.question, n_results=5)
                pref_context = self.context_store.get_preference_context(event.question)
                combined = list(dict.fromkeys(context + pref_context))[:5]
                event.context = combined

                suggestion = await loop.run_in_executor(
                    None, self.summarizer.generate_suggestion, event, combined
                )
                event.suggestion = suggestion

                self.session.trigger_events.append(event)
                await self.notifier.send_trigger_alert(event)

                for cb in self._event_callbacks:
                    try:
                        await cb(event)
                    except Exception:
                        pass

                self._status = "listening"
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SessionManager] Event loop error: {e}")
                self._status = "listening"

    def _on_silence_end(self):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(self.stop_meeting(), loop)

    def _save_transcript(self, session: MeetingSession):
        path = Path(config.TRANSCRIPTS_DIR)
        path.mkdir(parents=True, exist_ok=True)
        fname = path / f"{session.id}_{session.start_time.strftime('%Y%m%d_%H%M')}.json"
        data = {
            "id": session.id,
            "title": session.title,
            "start": session.start_time.isoformat(),
            "end": session.end_time.isoformat() if session.end_time else None,
            "attendees": session.attendees,
            "transcript": [
                {"speaker": c.speaker, "text": c.text, "timestamp": c.timestamp}
                for c in session.transcript
            ],
        }
        with open(fname, "w") as f:
            json.dump(data, f, indent=2)


_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
