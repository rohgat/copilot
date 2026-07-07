from __future__ import annotations
import asyncio
import numpy as np
import sounddevice as sd
from typing import Optional
from .config import config


class AudioCapture:
    """Captures system audio from BlackHole 2ch virtual device."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._stream: Optional[sd.InputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._last_rms: float = 0.0

    def find_device(self) -> int:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if config.AUDIO_DEVICE_NAME.lower() in d["name"].lower():
                if d["max_input_channels"] > 0:
                    return i
        available = [d["name"] for d in devices if d["max_input_channels"] > 0]
        raise RuntimeError(
            f"Audio device '{config.AUDIO_DEVICE_NAME}' not found.\n"
            f"Available input devices: {available}\n"
            "Install BlackHole 2ch from https://existentialcrisis.com/blackhole"
        )

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            pass
        audio = indata.copy().flatten().astype(np.float32)
        self._last_rms = float(np.sqrt(np.mean(audio**2)))
        if self._loop and not self._queue.full():
            asyncio.run_coroutine_threadsafe(self._queue.put(audio), self._loop)

    async def start(self):
        self._loop = asyncio.get_running_loop()
        device_id = self.find_device()
        block = config.AUDIO_SAMPLE_RATE * config.AUDIO_CHUNK_SECONDS
        self._stream = sd.InputStream(
            device=device_id,
            channels=1,
            samplerate=config.AUDIO_SAMPLE_RATE,
            blocksize=block,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self._running = True

    async def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def get_chunk(self) -> np.ndarray:
        return await self._queue.get()

    @property
    def rms_db(self) -> float:
        if self._last_rms == 0:
            return -100.0
        import math
        return 20 * math.log10(self._last_rms + 1e-10)

    @property
    def is_running(self) -> bool:
        return self._running
