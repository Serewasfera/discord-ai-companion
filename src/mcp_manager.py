import asyncio
import logging
import os
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from mcp.client.sse import sse_client
    HAS_SSE = True
except ImportError:
    HAS_SSE = False

log = logging.getLogger("mcp_manager")

@dataclass
class MCPServerCfg:
    name: str
    enabled: bool = True
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPCfg:
    enabled: bool = True
    call_timeout: float = 30.0
    max_iterations: int = 5
    servers: list[MCPServerCfg] = field(default_factory=list)


def _expand_env(value: str) -> str:
    if not isinstance(value, str):
        return value
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def load_mcp_config(path: str = "mcp_servers.yaml") -> MCPCfg:
    p = Path(path)
    if not p.exists():
        log.info(f"{path} не найден — MCP отключён")
        return MCPCfg(enabled=False)

    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    servers = []
    for name, srv in (raw.get("servers") or {}).items():
        env = {k: _expand_env(v) for k, v in (srv.get("env") or {}).items()}
        servers.append(MCPServerCfg(
            name=name,
            enabled=srv.get("enabled", True),
            command=srv.get("command"),
            args=[_expand_env(a) for a in (srv.get("args") or [])],
            env=env,
            url=srv.get("url"),
            headers=srv.get("headers") or {},
        ))

    return MCPCfg(
        enabled=raw.get("enabled", True),
        call_timeout=float(raw.get("call_timeout", 30.0)),
        max_iterations=int(raw.get("max_iterations", 5)),
        servers=servers,
    )

class MCPManager:

    def __init__(self, cfg: MCPCfg):
        self.cfg = cfg
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[str, str, dict]] = {}
        self._stack = AsyncExitStack()
        self._started = False

    async def start(self):
        if not self.cfg.enabled or self._started:
            return
        self._started = True

        for srv in self.cfg.servers:
            if not srv.enabled:
                continue
            try:
                await self._start_server(srv)
            except Exception as e:
                log.error(f"❌ MCP server '{srv.name}' failed to start: {e}")

        log.info(f"✅ MCP: {len(self._sessions)} серверов, {len(self._tools)} инструментов")

    async def _start_server(self, srv: MCPServerCfg):
        if srv.url:
            if not HAS_SSE:
                raise RuntimeError("mcp[sse] не установлен")
            transport = await self._stack.enter_async_context(
                sse_client(srv.url, headers=srv.headers or None)
            )
        else:
            params = StdioServerParameters(
                command=srv.command,
                args=srv.args,
                env={**os.environ, **srv.env},
            )
            transport = await self._stack.enter_async_context(stdio_client(params))

        read, write = transport
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools_resp = await session.list_tools()
        for tool in tools_resp.tools:
            prefixed = f"{srv.name}__{tool.name}"
            self._tools[prefixed] = (srv.name, tool.name, {
                "description": tool.description or "",
                "inputSchema": tool.inputSchema or {"type": "object", "properties": {}},
            })

        self._sessions[srv.name] = session
        log.info(f"  🔌 {srv.name}: {len(tools_resp.tools)} tools")

    async def stop(self):
        if not self._started:
            return
        try:
            await self._stack.aclose()
        except Exception as e:
            log.warning(f"MCP stop error: {e}")
        self._sessions.clear()
        self._tools.clear()
        self._started = False

    def get_openai_tools(self) -> list[dict]:
        result = []
        for prefixed, (_, _, meta) in self._tools.items():
            result.append({
                "type": "function",
                "function": {
                    "name": prefixed,
                    "description": meta["description"][:1024],
                    "parameters": meta["inputSchema"],
                },
            })
        return result

    async def call_tool(self, prefixed_name: str, arguments: dict) -> str:
        if prefixed_name not in self._tools:
            return f"Error: tool '{prefixed_name}' not found"

        server_name, tool_name, _ = self._tools[prefixed_name]
        session = self._sessions.get(server_name)
        if session is None:
            return f"Error: server '{server_name}' not running"

        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments),
                timeout=self.cfg.call_timeout,
            )
        except asyncio.TimeoutError:
            return f"Error: tool '{prefixed_name}' timed out after {self.cfg.call_timeout}s"
        except Exception as e:
            return f"Error calling '{prefixed_name}': {type(e).__name__}: {e}"

        parts = []
        for item in result.content:
            t = getattr(item, "type", None)
            if t == "text":
                parts.append(item.text)
            elif t == "image":
                parts.append("[image returned]")
            elif t == "resource":
                parts.append(f"[resource: {getattr(item, 'uri', '?')}]")
            else:
                parts.append(str(item))

        text = "\n".join(parts) if parts else "(no content)"
        if getattr(result, "isError", False):
            text = f"Tool returned error: {text}"
        return text

    @property
    def has_tools(self) -> bool:
        return bool(self._tools)