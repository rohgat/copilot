from __future__ import annotations
import anthropic
from typing import List, Optional
from .models import MeetingSession, MeetingSummary, TriggerEvent
from .config import config

_SUMMARY_PROMPT = """You are summarising a work meeting attended by {user_name}.

Meeting: {title}
Duration: {duration} minutes
Attendees: {attendees}

Full transcript:
{transcript}

Produce a structured summary in valid JSON:
{{
  "summary": "2-4 sentence overview of what was discussed and decided",
  "key_decisions": ["decision 1", "decision 2"],
  "action_items": ["person: task", "person: task"],
  "my_action_items": ["task assigned to {user_name}"],
  "open_questions": ["unanswered question 1"]
}}"""

_CATCHUP_PROMPT = """You are helping {user_name} catch up on a meeting they joined partway through.

Meeting: {title}
What was discussed BEFORE {user_name} joined:
{transcript_before}

Give {user_name} a concise catch-up in 3-5 bullet points covering: key decisions made, important context, and anything {user_name} needs to know to participate now.

Respond in plain text with bullet points starting with •"""

_SUGGESTION_PROMPT = """You are helping {user_name} respond in a meeting.

Question/request directed at {user_name}:
"{question}"
Asked by: {speaker}

Relevant context from past meetings and documents:
{context}

Draft a concise, confident spoken response (2-4 sentences) that {user_name} could say right now.
Be direct, professional. If context is insufficient, note that but still provide a sensible response.
Return plain text only — no headers, no bullet points."""

_WEEKLY_DIGEST_PROMPT = """You are creating a weekly meeting digest for {user_name}.

Meetings this week:
{meetings_text}

Produce a summary in JSON:
{{
  "week_summary": "2-3 sentence overview of the week's meetings",
  "open_action_items": ["my unresolved action items across all meetings"],
  "recurring_topics": ["topic that came up in multiple meetings"],
  "key_people": ["person: why they matter this week"]
}}"""


class Summarizer:
    """Generates meeting summaries, catch-ups, suggestions, and weekly digests."""

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def end_of_meeting(self, session: MeetingSession) -> MeetingSummary:
        transcript = session.full_transcript_text()
        if not transcript.strip():
            return MeetingSummary(
                meeting_id=session.id,
                title=session.title,
                summary="No transcript captured.",
                key_decisions=[],
                action_items=[],
                my_action_items=[],
                duration_minutes=session.duration_minutes(),
                attendees=session.attendees,
                date=session.start_time,
            )

        prompt = _SUMMARY_PROMPT.format(
            user_name=config.USER_NAME,
            title=session.title,
            duration=session.duration_minutes(),
            attendees=", ".join(session.attendees) or "Unknown",
            transcript=transcript[:12000],
        )
        import json
        resp = self._client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            data = json.loads(resp.content[0].text)
        except json.JSONDecodeError:
            data = {"summary": resp.content[0].text, "key_decisions": [], "action_items": [], "my_action_items": []}

        catchup = None
        if session.joined_late and session.late_join_index > 0:
            catchup = self.mid_call_catchup(session)

        return MeetingSummary(
            meeting_id=session.id,
            title=session.title,
            summary=data.get("summary", ""),
            key_decisions=data.get("key_decisions", []),
            action_items=data.get("action_items", []),
            my_action_items=data.get("my_action_items", []),
            catchup_summary=catchup,
            duration_minutes=session.duration_minutes(),
            attendees=session.attendees,
            date=session.start_time,
            notion_url=session.notion_url,
        )

    def mid_call_catchup(self, session: MeetingSession) -> str:
        before = session.transcript_before_join()
        if not before.strip():
            return "Nothing was discussed before you joined."

        prompt = _CATCHUP_PROMPT.format(
            user_name=config.USER_NAME,
            title=session.title,
            transcript_before=before[:8000],
        )
        resp = self._client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    def generate_suggestion(self, event: TriggerEvent, context: List[str]) -> str:
        context_text = "\n".join(f"- {c}" for c in context[:5]) if context else "No relevant past context found."
        prompt = _SUGGESTION_PROMPT.format(
            user_name=config.USER_NAME,
            question=event.question,
            speaker=event.speaker,
            context=context_text,
        )
        resp = self._client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    def pre_meeting_brief(self, title: str, attendees: List[str], description: str, past_context: List[str]) -> str:
        context_text = "\n".join(f"- {c}" for c in past_context[:8]) if past_context else "No past meeting history with these attendees."
        prompt = f"""Create a pre-meeting brief for {config.USER_NAME}.

Meeting: {title}
Attendees: {', '.join(attendees) or 'Unknown'}
Agenda/Description: {description or 'No agenda provided'}

Relevant past meeting context:
{context_text}

Write a brief (4-6 bullet points) covering:
• What's likely to be discussed based on past meetings
• Open action items from previous meetings with these attendees
• Key context {config.USER_NAME} should remember walking in
• Any decisions that were made last time that are relevant

Plain text with • bullet points."""

        resp = self._client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    def weekly_digest(self, summaries: List[MeetingSummary]) -> str:
        import json
        if not summaries:
            return "No meetings this week."

        meetings_text = ""
        for s in summaries:
            date_str = s.date.strftime("%A %b %d") if s.date else "Unknown date"
            meetings_text += f"\n---\n{date_str} — {s.title}\n"
            meetings_text += f"Summary: {s.summary}\n"
            if s.my_action_items:
                meetings_text += "My action items: " + "; ".join(s.my_action_items) + "\n"

        prompt = _WEEKLY_DIGEST_PROMPT.format(
            user_name=config.USER_NAME,
            meetings_text=meetings_text[:10000],
        )
        resp = self._client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return json.loads(resp.content[0].text)
        except json.JSONDecodeError:
            return resp.content[0].text
