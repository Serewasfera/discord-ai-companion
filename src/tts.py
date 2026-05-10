from openai import AsyncOpenAI
from .config import TTSCfg


class TTSClient:
    def __init__(self, cfg: TTSCfg):
        self.cfg = cfg
        self.client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    async def synthesize(self, text: str) -> bytes:
        resp = await self.client.audio.speech.create(
            model=self.cfg.model,
            voice=self.cfg.voice,
            input=text,
            response_format=self.cfg.response_format,
            speed=self.cfg.speed,
        )
        return resp.read() if hasattr(resp, "read") else resp.content