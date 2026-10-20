"""Agent 会话：多模态消息 + 工具调用循环（async，供 TUI 使用）。"""
from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI, OpenAI

from .config import Config
from . import skills as _skills
from .llm_backend import resolve as resolve_backend
from .tools import TOOL_SCHEMAS, ToolRunner, dispatch

DEFAULT_SYSTEM = """你是一名顶尖 CTF 选手，也是一个能调用工具的命令行助手。

你可以：
- 用 bash 跑一切命令行工具（file / strings / xxd / exiftool / binwalk / zsteg / 7z / curl / nc / python3 ...）
- 用 python 工具跑 Python3 片段（crypto/steg/pwn 脚本）
- 用 read_file / write_file 读写当前工作目录里的文件
- 用户粘贴的图片/视频帧会作为图片直接给你看

规则：
1. 先侦察再动手；每次只做一小步，看到输出再决定下一步。
2. 所有文件都在当前工作目录，附件已在这里。
3. 解出题目时调用 submit_flag 交候选 flag（需人工确认后才真正提交）。
4. 不要臆造 flag；拿不准就继续验证。
5. 回答简明，用中文。
"""


def _extract_reasoning(msg) -> str | None:
    """从模型响应里取思考内容（兼容 reasoning_content / reasoning 字段）。"""
    for attr in ("reasoning_content", "reasoning"):
        v = getattr(msg, attr, None)
        if v:
            return v
    extra = getattr(msg, "model_extra", None) or {}
    return extra.get("reasoning_content") or extra.get("reasoning")


class AgentSession:
    def __init__(self, cfg: Config, runner: ToolRunner, system_prompt: str | None = None,
                 session_id: str | None = None):
        self.cfg = cfg
        self.runner = runner
        self.session_id = session_id
        self._client = None
        self.backend = None
        self.mcp = None  # 由外部注入 MCPManager
        self.cancel_event = None  # 由 UI 注入 threading.Event，用于中止
        if system_prompt is None:
            system_prompt = (
                DEFAULT_SYSTEM
                + "\n\n可用技能手册（不确定怎么用时，先调 skill 工具查阅）：\n"
                + _skills.index()
            )
        self.system_prompt = system_prompt
        self.messages: list = [{"role": "system", "content": system_prompt}]
        self.pending_flag: str | None = None
        self.flag_reason: str = ""
        self.transcript: list[str] = []  # 供生成 WriteUp

    def _get_client(self):
        if self.backend is None:
            self.backend = resolve_backend(self.cfg, self.session_id)
        if not self.backend.api_key:
            raise RuntimeError(
                f"未配置 LLM：配置来源={self.cfg.source!r} backend={self.cfg.llm.backend!r} "
                f"model={self.cfg.llm.model!r}。请在 config.yaml 设置 llm.api_key，"
                "或设置 llm.backend: opencode-go（并确保 `opencode auth login`）；"
                "若配置来源显示「未找到配置」，说明启动时没读到 config.yaml，请用 `ctfcode` 启动。"
            )
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.backend.base_url,
                api_key=self.backend.api_key,
                default_headers=self.backend.headers,
            )
        return self._client

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.pending_flag = None
        self.flag_reason = ""
        self.transcript = []

    def set_system(self, text: str) -> None:
        self.system_prompt = text
        self.messages[0] = {"role": "system", "content": text}

    # ---------- 加用户消息 ----------
    def add_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
        self.transcript.append(f"[user] {text}")

    def add_user_multimodal(self, text: str, image_paths: list[str]) -> None:
        from .clipboard import image_data_url

        content: list = [{"type": "text", "text": text}]
        for p in image_paths:
            try:
                content.append({"type": "image_url", "image_url": {"url": image_data_url(p)}})
            except Exception:
                pass
        self.messages.append({"role": "user", "content": content})
        names = ", ".join(f"🖼{p.split('/')[-1]}" for p in image_paths)
        self.transcript.append(f"[user] {text} {names}")

    # ---------- 主循环 ----------
    def _sync_stream(self, tools: list, emit_ts, holder: dict) -> None:
        """在子线程里用同步客户端流式请求，绕过 httpx 异步流的清理 bug。"""
        client = OpenAI(
            base_url=self.backend.base_url,
            api_key=self.backend.api_key,
            default_headers=self.backend.headers,
            timeout=180,
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict] = {}
        r_started = c_started = False
        stream = client.chat.completions.create(
            model=self.backend.model,
            messages=self.messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            stream=True,
        )
        for chunk in stream:
            if self.cancel_event is not None and self.cancel_event.is_set():
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            r = getattr(delta, "reasoning_content", None)
            if r:
                if not r_started:
                    emit_ts("reasoning_start", None)
                    r_started = True
                reasoning_parts.append(r)
                emit_ts("reasoning_delta", r)
            c = getattr(delta, "content", None)
            if c:
                if not c_started:
                    emit_ts("assistant_start", None)
                    c_started = True
                content_parts.append(c)
                emit_ts("assistant_delta", c)
            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = tool_acc.setdefault(tc.index, {"id": None, "name": None, "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if fn.name:
                        slot["name"] = fn.name
                    if fn.arguments:
                        slot["args"] += fn.arguments
        holder["content"] = "".join(content_parts)
        holder["reasoning"] = "".join(reasoning_parts)
        holder["tool_acc"] = tool_acc

    async def _complete_stream(self, client, tools, emit) -> tuple[str, str, dict[int, dict]]:
        loop = asyncio.get_running_loop()

        def emit_ts(kind, payload):
            loop.call_soon_threadsafe(emit, kind, payload)

        holder: dict = {}
        await asyncio.to_thread(self._sync_stream, tools, emit_ts, holder)
        return holder.get("content", ""), holder.get("reasoning", ""), holder.get("tool_acc", {})

    async def _complete_once(self, client, tools) -> tuple[str, str, dict[int, dict]]:
        """非流式回退。"""
        resp = await client.chat.completions.create(
            model=self.backend.model, messages=self.messages,
            tools=tools, tool_choice="auto", temperature=0.2,
        )
        m = resp.choices[0].message
        tool_acc: dict[int, dict] = {}
        for idx, tc in enumerate(m.tool_calls or []):
            tool_acc[idx] = {"id": tc.id, "name": tc.function.name, "args": tc.function.arguments or ""}
        return m.content or "", _extract_reasoning(m) or "", tool_acc

    async def run(self, emit) -> str | None:
        """emit(kind, payload)。返回候选 flag。"""
        self.pending_flag = None
        self.flag_reason = ""
        client = self._get_client()
        tools = list(TOOL_SCHEMAS)
        if self.mcp is not None:
            tools += self.mcp.schemas()
        for _ in range(self.cfg.max_steps):
            if self.cancel_event is not None and self.cancel_event.is_set():
                break
            emit("thinking", None)
            streamed = True
            try:
                content, reasoning, tool_acc = await self._complete_stream(client, tools, emit)
            except Exception as e:  # noqa: BLE001  某些后端不支持 stream → 回退
                emit("stream_fallback", str(e))
                streamed = False
                content, reasoning, tool_acc = await self._complete_once(client, tools)
                # 回退没有逐块事件，这里把整段补发一次，保证界面能显示
                if reasoning:
                    emit("reasoning_start", None)
                    emit("reasoning_delta", reasoning)
                    emit("reasoning_end", None)
                if content:
                    emit("assistant_start", None)
                    emit("assistant_delta", content)
                    emit("assistant_end", None)

            if self.cancel_event is not None and self.cancel_event.is_set():
                break

            if streamed:
                if reasoning:
                    emit("reasoning_end", None)
                if content:
                    emit("assistant_end", None)
            if reasoning:
                self.transcript.append(f"[reasoning] {reasoning}")
            if content:
                self.transcript.append(f"[assistant] {content}")

            msg: dict = {"role": "assistant", "content": content or None}
            if tool_acc:
                msg["tool_calls"] = [
                    {"id": tool_acc[i]["id"], "type": "function",
                     "function": {"name": tool_acc[i]["name"], "arguments": tool_acc[i]["args"]}}
                    for i in sorted(tool_acc)
                ]
            self.messages.append(msg)
            if not tool_acc:
                break

            stop = False
            for i in sorted(tool_acc):
                slot = tool_acc[i]
                name = slot["name"]
                try:
                    args = json.loads(slot["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tc_id = slot["id"]
                if name == "submit_flag":
                    self.pending_flag = args.get("flag")
                    self.flag_reason = args.get("reason", "")
                    self.transcript.append(f"[flag] {self.pending_flag} ({self.flag_reason})")
                    emit("flag", {"flag": self.pending_flag, "reason": self.flag_reason})
                    self.messages.append({"role": "tool", "tool_call_id": tc_id, "content": "candidate recorded"})
                    stop = True
                else:
                    emit("tool_call", {"name": name, "args": args})
                    if self.mcp is not None and name in self.mcp.tool_names():
                        result = await self.mcp.call(name, args)
                    else:
                        result = await asyncio.to_thread(dispatch, self.runner, name, args)
                    self.transcript.append(f"[tool:{name}] {json.dumps(args, ensure_ascii=False)} -> {result[:1500]}")
                    emit("tool_result", {"name": name, "result": result})
                    self.messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
            if stop:
                break
        return self.pending_flag
