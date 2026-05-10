from collections import defaultdict, deque
from typing import Deque, Dict, List
from openai import AsyncOpenAI
from .config import LLMCfg, PersonaCfg


class LLMClient:
    def __init__(self, cfg: LLMCfg, persona: PersonaCfg):
        self.cfg = cfg
        self.persona = persona
        self.client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        self._history: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=cfg.history_size)
        )

    def _system_message(self) -> dict:
        content = (
            f"{self.persona.system_prompt}\n\n"
            f"=== Личность ===\n{self.persona.personality}"
        )
        return {"role": "system", "content": content}

    def _build_messages(self, key: str, user_text: str) -> List[dict]:
        msgs = [self._system_message()]
        msgs.extend(self._history[key])
        msgs.append({"role": "user", "content": user_text})
        return msgs

    async def chat(self, key: str, user_text: str) -> str:
        messages = self._build_messages(key, user_text)
        resp = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            frequency_penalty=self.cfg.frequency_penalty,
            presence_penalty=self.cfg.presence_penalty,
            max_tokens=self.cfg.max_tokens,
        )
        answer = resp.choices[0].message.content.strip()

        self._history[key].append({"role": "user", "content": user_text})
        self._history[key].append({"role": "assistant", "content": answer})
        return answer

    def reset(self, key: str):
        self._history[key].clear()