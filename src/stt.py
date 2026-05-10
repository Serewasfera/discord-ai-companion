import io
from openai import AsyncOpenAI
from .config import STTCfg


class STTClient:
    def __init__(self, cfg: STTCfg):
        self.cfg = cfg
        self.client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    async def transcribe(self, wav_bytes: bytes, filename: str = "audio.wav") -> str:
        bio = io.BytesIO(wav_bytes)
        bio.name = filename
        resp = await self.client.audio.transcriptions.create(
            model=self.cfg.model,
            file=bio,
            language=self.cfg.language,
        )
        return resp.text.strip()