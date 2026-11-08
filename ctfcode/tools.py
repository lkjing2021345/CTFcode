"""暴露给 LLM 的工具（函数调用）与执行器。

所有操作限定在参赛题目的工作目录内，带超时，简单危险命令拦截。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys

from . import skills as _skills

# 简单危险命令拦截（不是安全边界，只是防手滑）
_DENY = [
    "rm -rf /",
    "mkfs",
    ":(){",
    "dd if=/dev/zero",
    "> /dev/sd",
    "chmod -R 777 /",
]

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # OpenAI 单图上限约 20MB

# ── 提供给 LLM 的工具 schema ──
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "在题目工作目录里执行一条 shell 命令。用于 file / strings / xxd / binwalk / "
                "zsteg / exiftool / 7z / python3 等一切命令行工具。返回 stdout+stderr。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 60"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作目录里的文件（文本，或二进制的前若干字节的十六进制）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把文本内容写入工作目录里的文件（用于写脚本）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python",
            "description": "执行一段 Python3 代码（stdin 方式），适合写加密/隐写/解题脚本。",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_image",
            "description": (
                "查看工作目录里的图片（png/jpg/jpeg/webp/gif/bmp），把图片真正交给多模态模型。"
                "需要观察题目配图、截图、隐写图片时调用；read_file 只能读到十六进制，看不到画面。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片路径，相对当前工作目录"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill",
            "description": (
                "查阅某个 CTF 工具用法手册(skill)。不确定用什么工具、或需要某方向的标准套路时先调用它。"
                "name 留空则列出所有可用技能。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名，如 misc/stego/crypto/web/reverse/pwn/forensics/mobile/vmimage"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_flag",
            "description": "当你确信已解出题目时，交出最终候选 flag（只会被记录，等待人工确认后才会真正提交）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "flag": {"type": "string"},
                    "reason": {"type": "string", "description": "简述怎么得到的"},
                },
                "required": ["flag"],
            },
        },
    },
]


class ToolRunner:
    def __init__(self, workdir: str, bash_timeout: int = 60):
        self.workdir = os.path.abspath(workdir)
        self.bash_timeout = bash_timeout
        # 让题目里跑的 python3/pip 用带 CTF 库的解释器（Agent 自身的 venv）
        self.bindir = os.path.dirname(os.path.abspath(sys.executable))
        self.python = sys.executable
        os.makedirs(self.workdir, exist_ok=True)

    def _env(self) -> dict:
        env = os.environ.copy()
        env["PATH"] = self.bindir + os.pathsep + env.get("PATH", "")
        env.setdefault("VIRTUAL_ENV", os.path.dirname(self.bindir))
        return env

    # ---------- 路径安全 ----------
    def _resolve(self, path: str) -> str:
        p = os.path.abspath(os.path.join(self.workdir, path))
        if not (p == self.workdir or p.startswith(self.workdir + os.sep)):
            raise ValueError(f"路径越界，仅允许工作目录内: {path}")
        return p

    # ---------- 工具实现 ----------
    def bash(self, command: str, timeout: int | None = None) -> str:
        for bad in _DENY:
            if bad in command:
                return f"[blocked] 危险命令被拦截: {bad}"
        timeout = timeout or self.bash_timeout
        try:
            p = subprocess.run(
                command, shell=True, cwd=self.workdir,
                capture_output=True, text=True, timeout=timeout, env=self._env(),
            )
            out = p.stdout or ""
            if p.stderr:
                out += "\n[stderr]\n" + p.stderr
            out = out.strip() or "(无输出)"
            return f"[exit {p.returncode}]\n{out[:8000]}"
        except subprocess.TimeoutExpired:
            return f"[timeout] 超过 {timeout}s 未结束"
        except Exception as e:  # noqa: BLE001
            return f"[error] {e}"

    def resolve_image(self, path: str) -> str:
        """校验并返回工作目录内图片的绝对路径，供多模态消息使用。"""
        p = self._resolve(path)
        if not os.path.isfile(p):
            raise ValueError(f"图片不存在: {path}")
        ext = os.path.splitext(p)[1].lower()
        if ext not in IMAGE_EXT:
            raise ValueError(f"不是支持的图片格式: {ext or '(无扩展名)'}")
        size = os.path.getsize(p)
        if size > MAX_IMAGE_BYTES:
            raise ValueError(f"图片过大: {size / 1024 / 1024:.1f}MB（上限 20MB）")
        if size == 0:
            raise ValueError(f"图片是空文件: {path}")
        return p

    def read_file(self, path: str, max_bytes: int = 20000) -> str:
        p = self._resolve(path)
        if not os.path.exists(p):
            return f"[not found] {path}"
        with open(p, "rb") as f:
            data = f.read(max_bytes)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.hex(" ")

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        os.makedirs(os.path.dirname(p) or self.workdir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[ok] 已写入 {path}"

    def python(self, code: str) -> str:
        return self.bash(f"{shlex.quote(self.python)} - <<'PYEOF'\n{code}\nPYEOF")


def dispatch(runner: ToolRunner, name: str, args: dict) -> str:
    try:
        if name == "bash":
            return runner.bash(args["command"], args.get("timeout"))
        if name == "read_file":
            return runner.read_file(args["path"])
        if name == "write_file":
            return runner.write_file(args["path"], args["content"])
        if name == "python":
            return runner.python(args["code"])
        if name == "skill":
            return _skills.handle(args.get("name", ""))
        return f"[error] 未知工具 {name}"
    except Exception as e:  # noqa: BLE001
        return f"[error] {e}"
