from __future__ import annotations
import asyncio
import json
import time
from typing import Optional, List
import anthropic
from .models import TranscriptChunk, TriggerEvent
from .config import config

_SYSTEM = """You are a meeting monitor for {user_name}. Your job is to detect when {user_name} is directly addressed or asked a question in a meeting transcript.

Respond ONLY with valid JSON in this exact format:
{{
  "triggered": true,
  "question": "exact question or request directed at {user_name}",
  "speaker": "name of the person who spoke",
  "confidence": 0.85,
  "intent": "question|action_request|mention|decision"
}}

OR if not triggered:
{{
  "triggered": false,
  "confidence": 0.0
}}

Rules:
- triggered=true ONLY when {user_name} is specifically addressed AND something is expected from them
- "question" should be the full verbatim sentence
- confidence: 0.0-1.0 based on how clear the trigger is
- Do NOT trigger for casual mentions, third-party references, or past-tense references"""


class Detector:
    """Monitors transcript stream for name + intent triggers using Claude."""

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._buffer: List[str] = []
        self._task: Optional[asyncio.Task] = None
        self._last_trigger_time: float = 0.0
        self._cooldown_seconds: float = 8.0  # avoid double-triggering same event

    async def start(self, transcriber, meeting_id: str):
        self._task = asyncio.create_task(
            self._detect_loop(transcriber, meeting_id)
        )

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _detect_loop(self, transcriber, meeting_id: str):
        loop = asyncio.get_running_loop()
        while True:
            chunk: TranscriptChunk = await transcriber.get_chunk()
            line = f"{chunk.speaker}: {chunk.text}"
            self._buffer.append(line)
            if len(self._buffer) > config.TRANSCRIPT_BUFFER_LINES:
                self._buffer.pop(0)

            name_lower = config.USER_NAME.lower()
            if name_lower not in chunk.text.lower():
                continue

            now = time.time()
            if now - self._last_trigger_time < self._cooldown_seconds:
                continue

            window = "\n".join(self._buffer[-12:])
            event = await loop.run_in_executor(
                None, self._call_claude, window, meeting_id
            )
            if event:
                self._last_trigger_time = now
                await self._queue.put(event)

    def _call_claude(self, window: str, meeting_id: str) -> Optional[TriggerEvent]:
        system = _SYSTEM.format(user_name=config.USER_NAME)
        prompt = f"Meeting transcript (most recent at bottom):\n\n{window}\n\nDoes this transcript contain a trigger directed at {config.USER_NAME}?"
        try:
            resp = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=300,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(resp.content[0].text)
            if (
                data.get("triggered")
                and data.get("confidence", 0) >= config.DETECTION_CONFIDENCE_THRESHOLD
            ):
                return TriggerEvent(
                    meeting_id=meeting_id,
                    question=data.get("question", ""),
                    speaker=data.get("speaker", "Unknown"),
                    context=[],
                    suggestion="",
                    confidence=data.get("confidence", 0.8),
                    timestamp=time.time(),
                )
        except (json.JSONDecodeError, KeyError, Exception):
            pass
        return None

    async def get_event(self) -> TriggerEvent:
        return await self._queue.get()
