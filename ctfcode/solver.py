"""Agent 主循环：把题目交给 LLM，让它调用工具解题，最后交出候选 flag。"""
from __future__ import annotations

import json

from openai import OpenAI

from .config import Config
from . import skills as _skills
from .llm_backend import resolve as resolve_backend
from .tools import TOOL_SCHEMAS, ToolRunner, dispatch

SYSTEM_PROMPT = """你是一名顶尖 CTF 选手。你只能通过提供的工具工作。

规则：
1. 拿到题目后，先用 bash 做侦察（file / strings / xxd / exiftool / binwalk 等），再决定方向。
2. 写脚本用 python 工具或 write_file + bash 运行。
3. 所有文件都在当前工作目录内，附件已下载在这里。
4. 当你有把握时，调用 submit_flag 交候选 flag（flag 通常形如 flag{...} 或 平台给定前缀）。
5. 不要臆造 flag；拿不准就继续验证。每次只做一小步，看到输出再决定下一步。
6. 简明扼要，不要输出无关的长篇解释。
"""


def _build_user_prompt(challenge, detail: dict, files: list[str]) -> str:
    desc = detail.get("description", "") or "(无描述)"
    hints = detail.get("hints") or []
    ctx = detail.get("context") or {}
    lines = [
        f"题目名称：{challenge.title}",
        f"类别：{challenge.category}",
        f"分值：{challenge.score}，已解出 {challenge.solved_count}",
        "",
        "题目描述：",
        desc,
    ]
    if hints:
        lines += ["", "提示：", *[f"- {h}" for h in hints]]
    if ctx.get("instanceEntry"):
        lines += ["", f"容器/实例入口：{ctx['instanceEntry']}"]
    if files:
        lines += ["", "已下载到工作目录的附件：", *[f"- {f}" for f in files]]
    else:
        lines += ["", "（本题无附件）"]
    return "\n".join(lines)


def solve(cfg: Config, runner: ToolRunner, challenge, detail: dict, files: list[str], log=print) -> str | None:
    """返回候选 flag 或 None。"""
    backend = resolve_backend(cfg)
    client = OpenAI(base_url=backend.base_url, api_key=backend.api_key,
                    default_headers=backend.headers)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n可用技能手册（用 skill 工具查阅）：\n" + _skills.index()},
        {"role": "user", "content": _build_user_prompt(challenge, detail, files)},
    ]

    candidate: str | None = None
    for step in range(cfg.max_steps):
        resp = client.chat.completions.create(
            model=backend.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            # 模型没再调用工具，结束
            if msg.content:
                log(f"    [模型] {msg.content[:300]}")
            break

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "submit_flag":
                candidate = args.get("flag")
                log(f"    [候选 flag] {candidate}  （理由：{args.get('reason', '')}）")
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": "candidate recorded",
                })
            else:
                log(f"    [工具] {name}: {str(args)[:160]}")
                result = dispatch(runner, name, args)
                log(f"      -> {result[:200].replace(chr(10), ' ')}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if candidate:
            break

    return candidate
