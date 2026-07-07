from __future__ import annotations
import asyncio
import time
from typing import Optional
import numpy as np
from .models import TranscriptChunk
from .config import config


class Transcriber:
    """Streams audio chunks through faster-whisper and emits TranscriptChunks."""

    def __init__(self):
        self._model = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def _load_model(self):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            config.WHISPER_MODEL,
            device="auto",  # uses CoreML/Metal on Apple Silicon
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )

    async def start(self, audio_capture, meeting_id: str):
        if self._model is None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_model)
        self._task = asyncio.create_task(
            self._transcribe_loop(audio_capture, meeting_id)
        )

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _transcribe_loop(self, audio_capture, meeting_id: str):
        loop = asyncio.get_running_loop()
        while True:
            chunk: np.ndarray = await audio_capture.get_chunk()
            segments = await loop.run_in_executor(
                None, self._transcribe_chunk, chunk
            )
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                tc = TranscriptChunk(
                    meeting_id=meeting_id,
                    speaker="Speaker",
                    text=text,
                    timestamp=time.time(),
                    start=seg.start,
                    end=seg.end,
                )
                await self._queue.put(tc)

    def _transcribe_chunk(self, audio: np.ndarray):
        segments, _ = self._model.transcribe(
            audio,
            beam_size=5,
            language="en",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return list(segments)

    async def get_chunk(self) -> TranscriptChunk:
        return await self._queue.get()
