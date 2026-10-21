"""Anthropic 原生后端：把 OpenAI 风格的消息/工具翻译成 Messages API。

只做协议转换，不改变上层 Agent 的数据结构（仍以 OpenAI 风格保存历史）。
"""
from __future__ import annotations

import json

DEFAULT_MAX_TOKENS = 4096


def convert_tools(schemas: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in schemas or []:
        f = s.get("function") or {}
        out.append({
            "name": f.get("name"),
            "description": (f.get("description") or "")[:1024],
            "input_schema": f.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _user_blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    blocks: list[dict] = []
    for part in content or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if isinstance(url, str) and url.startswith("data:"):
                head, _, b64 = url.partition(",")
                media = head[5:].split(";")[0] or "image/png"
                blocks.append({"type": "image", "source": {
                    "type": "base64", "media_type": media, "data": b64,
                }})
    return blocks or [{"type": "text", "text": ""}]


def convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    out: list[dict] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "system":
            c = m.get("content")
            if isinstance(c, str):
                system_parts.append(c)
            continue
        if role == "user":
            out.append({"role": "user", "content": _user_blocks(m.get("content"))})
        elif role == "assistant":
            blocks: list[dict] = []
            c = m.get("content")
            if isinstance(c, str) and c:
                blocks.append({"type": "text", "text": c})
            for tc in m.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                try:
                    inp = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    inp = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "input": inp,
                })
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        elif role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id"),
                "content": m.get("content") or "",
            }
            if out and out[-1]["role"] == "user":
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})

    merged: list[dict] = []
    for msg in out:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"].extend(msg["content"])
        else:
            merged.append({"role": msg["role"], "content": list(msg["content"])})
    return "\n\n".join(system_parts), merged


async def stream_chat(client, *, model: str, system: str, messages: list[dict],
                      tools: list[dict], emit, max_tokens: int = DEFAULT_MAX_TOKENS,
                      thinking: bool = False) -> tuple[str, str, dict[int, dict]]:
    kwargs: dict = {
        "model": model,
        "system": system or "You are a helpful CTF assistant.",
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
    else:
        kwargs["temperature"] = 0.2

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    r_started = c_started = False

    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            etype = getattr(event, "type", "")
            if etype == "content_block_start":
                block = getattr(event, "content_block", None)
                idx = getattr(event, "index", 0)
                if getattr(block, "type", "") == "tool_use":
                    tool_acc[idx] = {"id": block.id, "name": block.name, "args": ""}
                elif getattr(block, "type", "") == "thinking" and not r_started:
                    emit("reasoning_start", None)
                    r_started = True
            elif etype == "content_block_delta":
                d = getattr(event, "delta", None)
                dt = getattr(d, "type", "")
                if dt == "thinking_delta":
                    if not r_started:
                        emit("reasoning_start", None)
                        r_started = True
                    reasoning_parts.append(d.thinking)
                    emit("reasoning_delta", d.thinking)
                elif dt == "text_delta":
                    if not c_started:
                        emit("assistant_start", None)
                        c_started = True
                    content_parts.append(d.text)
                    emit("assistant_delta", d.text)
                elif dt == "input_json_delta":
                    slot = tool_acc.setdefault(getattr(event, "index", 0),
                                               {"id": None, "name": None, "args": ""})
                    slot["args"] += d.partial_json

    return "".join(content_parts), "".join(reasoning_parts), tool_acc


async def once_chat(client, *, model: str, system: str, messages: list[dict],
                    tools: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS,
                    thinking: bool = False) -> tuple[str, str, dict[int, dict]]:
    kwargs: dict = {
        "model": model,
        "system": system or "You are a helpful CTF assistant.",
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
    else:
        kwargs["temperature"] = 0.2

    resp = await client.messages.create(**kwargs)
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    for i, block in enumerate(getattr(resp, "content", []) or []):
        bt = getattr(block, "type", "")
        if bt == "text":
            content_parts.append(block.text)
        elif bt == "thinking":
            reasoning_parts.append(block.thinking)
        elif bt == "tool_use":
            tool_acc[i] = {
                "id": block.id,
                "name": block.name,
                "args": json.dumps(block.input, ensure_ascii=False),
            }
    return "".join(content_parts), "".join(reasoning_parts), tool_acc
