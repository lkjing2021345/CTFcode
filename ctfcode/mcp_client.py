"""MCP 客户端：连接外部 MCP 服务器（如 Burp 的 MCP 扩展），把它们的工具暴露给 Agent。

支持传输：sse / streamable-http / stdio。
配置（config.yaml）：
    mcp:
      burp:
        transport: sse
        url: "http://127.0.0.1:9876/sse"
      demo:
        transport: stdio
        command: python3
        args: ["/path/to/server.py"]
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

from mcp import ClientSession


class MCPManager:
    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[ClientSession, str]] = {}  # fullname -> (session, 真实工具名)
        self._schemas: list[dict] = []
        self.errors: dict[str, str] = {}

    # ---------- 连接 ----------
    async def connect_all(self, configs: dict) -> None:
        for name, cfg in (configs or {}).items():
            if cfg.get("enabled", True) is False:
                continue
            timeout = float(cfg.get("timeout", 15))
            try:
                await asyncio.wait_for(self._connect_one(name, cfg), timeout=timeout)
            except TimeoutError:
                self.errors[name] = f"连接超时（{timeout}s）——服务没开或地址不对"
            except Exception as e:  # noqa: BLE001
                self.errors[name] = str(e)

    async def _connect_one(self, name: str, cfg: dict) -> None:
        transport = (cfg.get("transport") or "sse").lower()
        if transport in ("sse",):
            from mcp.client.sse import sse_client

            read, write = await self._stack.enter_async_context(sse_client(cfg["url"]))
        elif transport in ("http", "streamable-http", "streamable_http"):
            from mcp.client.streamable_http import streamable_http_client

            res = await self._stack.enter_async_context(streamable_http_client(cfg["url"]))
            read, write = res[0], res[1]
        elif transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(
                command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env")
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
        else:
            raise ValueError(f"未知 transport: {transport}")

        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self.sessions[name] = session

        resp = await session.list_tools()
        for t in resp.tools:
            full = f"{name}__{t.name}"
            self._tools[full] = (session, t.name)
            schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
            self._schemas.append({
                "type": "function",
                "function": {
                    "name": full,
                    "description": (t.description or f"MCP tool {t.name} from {name}")[:1024],
                    "parameters": schema,
                },
            })

    # ---------- 暴露给 LLM ----------
    def schemas(self) -> list[dict]:
        return self._schemas

    def tool_names(self) -> set[str]:
        return set(self._tools)

    def summary(self) -> str:
        lines = []
        for name, s in self.sessions.items():
            n = sum(1 for f in self._tools if f.startswith(name + "__"))
            lines.append(f"  [OK] {name}: {n} 个工具")
        for name, err in self.errors.items():
            lines.append(f"  [失败] {name}: {err}")
        return "\n".join(lines) if lines else "  (未配置 MCP 服务器)"

    # ---------- 调用 ----------
    async def call(self, fullname: str, args: dict) -> str:
        if fullname not in self._tools:
            return f"[error] 未知 MCP 工具 {fullname}"
        session, real = self._tools[fullname]
        try:
            result = await session.call_tool(real, args)
        except Exception as e:  # noqa: BLE001
            return f"[error] 调用 {fullname} 失败: {e}"
        parts = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(str(item))
        out = "\n".join(parts) if parts else "(无返回)"
        if getattr(result, "isError", False):
            out = "[工具报错] " + out
        return out[:8000]

    async def close(self) -> None:
        try:
            await self._stack.aclose()
        except Exception:  # noqa: BLE001
            pass
