import asyncio
import io
import os
import tempfile
import time
import wave
from typing import Dict

import discord
from discord.ext import voice_recv

from .config import VoiceCfg
from .stt import STTClient
from .tts import TTSClient
from .llm import LLMClient


class PerUserBuffer:

    def __init__(self):
        self.chunks: list[bytes] = []
        self.last_packet_ts: float = 0.0

    def add(self, pcm: bytes):
        if not pcm:
            return
        self.chunks.append(pcm)
        self.last_packet_ts = time.monotonic()

    def has_data(self) -> bool:
        return bool(self.chunks)

    def duration_ms(self) -> int:
        total = sum(len(c) for c in self.chunks)
        # PCM 48 кГц stereo s16 -> 4 байта/сэмпл
        return int(total / (48000 * 4) * 1000)

    def silence_ms(self) -> int:
        if not self.chunks:
            return 0
        return int((time.monotonic() - self.last_packet_ts) * 1000)

    def take_wav(self, sample_rate: int = 48000) -> bytes:
        pcm = b"".join(self.chunks)
        self.chunks.clear()
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return bio.getvalue()


class VoiceSession:
    def __init__(
        self,
        vc: voice_recv.VoiceRecvClient,
        llm: LLMClient,
        stt: STTClient,
        tts: TTSClient,
        cfg: VoiceCfg,
        text_channel: discord.TextChannel | None = None,
    ):
        self.vc = vc
        self.llm = llm
        self.stt = stt
        self.tts = tts
        self.cfg = cfg
        self.text_channel = text_channel
        self.buffers: Dict[int, PerUserBuffer] = {}
        self._watcher_task: asyncio.Task | None = None
        self._loop = asyncio.get_event_loop()
        self._busy = False

    def start(self):
        sink = voice_recv.BasicSink(self._on_voice)
        self.vc.listen(sink)
        self._watcher_task = asyncio.create_task(self._watcher())
        print("[VoiceSession] Listening")

    def stop(self):
        try:
            if self.vc.is_listening():
                self.vc.stop_listening()
        except Exception as e:
            print(f"[VoiceSession.stop] {e}")
        if self._watcher_task:
            self._watcher_task.cancel()

    def _on_voice(self, user: discord.User | None, data: voice_recv.VoiceData):
        if user is None or user.bot:
            return
        pcm = getattr(data, "pcm", None)
        if not pcm:
            return
        buf = self.buffers.setdefault(user.id, PerUserBuffer())
        buf.add(pcm)

    async def _watcher(self):
        try:
            while True:
                await asyncio.sleep(0.2)
                if self._busy:
                    continue
                for user_id, buf in list(self.buffers.items()):
                    if not buf.has_data():
                        continue
                    if (
                        buf.silence_ms() >= self.cfg.silence_threshold_ms
                        and buf.duration_ms() >= self.cfg.min_audio_length_ms
                    ):
                        wav = buf.take_wav(self.cfg.sample_rate)
                        asyncio.create_task(self._handle_utterance(user_id, wav))
        except asyncio.CancelledError:
            pass

    async def _handle_utterance(self, user_id: int, wav_bytes: bytes):
        if self._busy:
            return
        self._busy = True
        try:
            text = await self.stt.transcribe(wav_bytes)
            if not text:
                return
            print(f"[STT] <{user_id}> {text}")

            answer = await self.llm.chat(f"voice:{user_id}", text)
            print(f"[LLM] {answer}")

            if self.text_channel:
                await self.text_channel.send(
                    f"🗣️ <@{user_id}>: {text}\n🤖 {answer}"
                )

            audio = await self.tts.synthesize(answer)
            await self._play_audio(audio)
        except Exception as e:
            print(f"[VoiceSession] error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._busy = False

    async def _play_audio(self, audio_bytes: bytes):
        with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as f:
            f.write(audio_bytes)
            path = f.name

        try:
            source = discord.FFmpegPCMAudio(path)
            done = asyncio.Event()

            def _after(_err):
                self._loop.call_soon_threadsafe(done.set)

            self.vc.play(source, after=_after)
            await done.wait()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass