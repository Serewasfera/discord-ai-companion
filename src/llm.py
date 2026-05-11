import asyncio
import json
import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, List

from openai import AsyncOpenAI

from .config import LLMCfg, PersonaCfg
from .mcp_manager import MCPManager


log = logging.getLogger("llm")

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _key_to_filename(key: str) -> str:
    return _SAFE_NAME_RE.sub("_", key) + ".json"


def _filename_to_key(name: str) -> str:
    stem = name[:-5] if name.endswith(".json") else name

    if stem.startswith("text_"):
        return "text:" + stem[5:]
    if stem.startswith("voice_"):
        return "voice:" + stem[6:]
    return stem


class LLMClient:
    def __init__(
        self,
        cfg: LLMCfg,
        persona: PersonaCfg,
        mcp: MCPManager | None = None,
    ):
        self.cfg = cfg
        self.persona = persona
        self.mcp = mcp
        self.client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

        self._history: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=cfg.history_size)
        )

        self.history_dir = Path(cfg.history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._save_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._load_all_histories()

    def _history_file(self, key: str) -> Path:
        return self.history_dir / _key_to_filename(key)

    def _load_all_histories(self):
        loaded = 0
        for f in self.history_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    continue
                key = _filename_to_key(f.name)
                dq = self._history[key]

                for msg in data[-self.cfg.history_size:]:
                    dq.append(msg)
                loaded += 1
            except Exception as e:
                log.warning(f"Failed to load history {f.name}: {e}")
        if loaded:
            log.info(f"📚 Загружено {loaded} историй из {self.history_dir}")

    async def _save_history(self, key: str):
        async with self._save_locks[key]:
            try:
                target = self._history_file(key)
                tmp = target.with_suffix(".json.tmp")
                data = list(self._history[key])
                tmp.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                tmp.replace(target)
            except Exception as e:
                log.warning(f"Failed to save history {key}: {e}")

    def _system_message(self) -> dict:
        content = (
            f"{self.persona.system_prompt}\n\n"
            f"=== Личность ===\n{self.persona.personality}"
        )
        if self.mcp and self.mcp.has_tools:
            content += (
                "\n\nУ тебя есть доступ к инструментам. "
                "Используй их когда требуется актуальная информация, "
                "поиск, файлы или внешние действия. "
                "Не упоминай явно названия инструментов в ответе пользователю."
            )
        return {"role": "system", "content": content}

    def _build_messages(self, key: str, user_text: str) -> List[dict]:
        msgs = [self._system_message()]
        msgs.extend(self._history[key])
        msgs.append({"role": "user", "content": user_text})
        return msgs

    async def chat(self, key: str, user_text: str) -> str:
        messages = self._build_messages(key, user_text)
        tools = self.mcp.get_openai_tools() if self.mcp and self.mcp.has_tools else None

        new_history_entries = [{"role": "user", "content": user_text}]

        max_iter = self.mcp.cfg.max_iterations if self.mcp else 1
        final_text = ""

        for _ in range(max_iter):
            kwargs = dict(
                model=self.cfg.model,
                messages=messages,
                temperature=self.cfg.temperature,
                top_p=self.cfg.top_p,
                frequency_penalty=self.cfg.frequency_penalty,
                presence_penalty=self.cfg.presence_penalty,
                max_tokens=self.cfg.max_tokens,
            )
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            resp = await self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            if msg.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                messages.append(assistant_msg)
                new_history_entries.append(assistant_msg)

                async def _call(tc):
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    log.info(f"🔧 tool: {tc.function.name}({args})")
                    result = await self.mcp.call_tool(tc.function.name, args)
                    return tc.id, result

                results = await asyncio.gather(*[_call(tc) for tc in msg.tool_calls])

                for tc_id, result in results:
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result[:8000],
                    }
                    messages.append(tool_msg)
                    new_history_entries.append(tool_msg)

                continue

            final_text = (msg.content or "").strip()
            new_history_entries.append({
                "role": "assistant",
                "content": final_text,
            })
            break
        else:
            final_text = "(достигнут лимит итераций tool calling)"

        for entry in new_history_entries:
            self._history[key].append(entry)

        await self._save_history(key)
        return final_text

    def reset(self, key: str):
        self._history[key].clear()
        f = self._history_file(key)
        if f.exists():
            try:
                f.unlink()
            except OSError as e:
                log.warning(f"Failed to delete {f}: {e}")