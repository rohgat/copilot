from __future__ import annotations
import asyncio
import time
from typing import Optional, Callable
from .config import config


class SilenceDetector:
    """Monitors audio RMS levels and fires a callback after sustained silence."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None
        self._last_sound_time: float = time.time()

    async def start(self, audio_capture, on_silence_end: Callable):
        self._callback = on_silence_end
        self._last_sound_time = time.time()
        self._task = asyncio.create_task(self._monitor_loop(audio_capture))

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self, audio_capture):
        while True:
            await asyncio.sleep(2)
            db = audio_capture.rms_db
            if db > config.SILENCE_THRESHOLD_DB:
                self._last_sound_time = time.time()
            else:
                silent_for = time.time() - self._last_sound_time
                if silent_for >= config.SILENCE_DURATION_SECONDS:
                    if self._callback:
                        self._callback()
                    break
