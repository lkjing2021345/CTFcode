"""会话持久化：每个会话一个 JSON 文件，支持列表/加载/保存/新建。

存放目录默认 ~/.local/share/gzctf-agent/sessions/（可用 config 的 ui.sessions_dir 覆盖）。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


def now_ms() -> int:
    return int(time.time() * 1000)


def fmt_time(ms: int) -> str:
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(ms / 1000))
    except Exception:
        return "?"


class SessionStore:
    def __init__(self, root: str):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, sid: str) -> Path:
        return self.root / f"{sid}.json"

    def new_id(self) -> str:
        return "ses_" + uuid.uuid4().hex[:12]

    def list(self) -> list[dict]:
        out: list[dict] = []
        for p in self.root.glob("*.json"):
            try:
                d = json.loads(p.read_text("utf-8"))
            except Exception:
                continue
            out.append({
                "id": d.get("id", p.stem),
                "title": d.get("title") or "(无标题)",
                "updated": d.get("updated", 0),
                "count": len(d.get("messages", []) or []),
            })
        out.sort(key=lambda x: x["updated"], reverse=True)
        return out

    def load(self, sid: str) -> dict | None:
        p = self.path(sid)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return None

    def save(self, data: dict) -> None:
        data["updated"] = now_ms()
        self.path(data["id"]).write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    def delete(self, sid: str) -> None:
        try:
            self.path(sid).unlink()
        except FileNotFoundError:
            pass
