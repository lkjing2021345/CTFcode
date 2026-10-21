"""LLM 后端解析。

支持两种：
1. 普通 OpenAI 兼容端点（config.yaml 里填 base_url + api_key）。
2. 直接复用本机 OpenCode 的登录凭证连 OpenCode Go / OpenCode：
   llm.backend: "opencode-go"  或  "opencode"
   运行时会调用 `opencode auth export` 动态取 token，并自动补上
   x-opencode-session / x-opencode-org-id / User-Agent 等必要请求头。
"""
from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field

import requests

from . import providers as providers_mod
from .config import Config

GO_BASE = {
    "opencode-go": "https://opencode.ai/inference/go/openai/v1",
    "opencode": "https://opencode.ai/inference/openai/v1",
}


@dataclass
class LLMBackend:
    base_url: str
    api_key: str
    model: str
    headers: dict = field(default_factory=dict)
    label: str = "custom"
    extra_body: dict = field(default_factory=dict)


def _opencode_export() -> list:
    out = subprocess.run(
        ["opencode", "auth", "export"], capture_output=True, text=True, timeout=20
    ).stdout
    return json.loads(out)


def _pick_credential(integration: str = "opencode") -> dict | None:
    try:
        creds = _opencode_export()
    except Exception:
        return None
    # 优先匹配 integration，其次任意 active
    for c in creds:
        v = c.get("value") or {}
        if c.get("integrationID") == integration and v.get("access"):
            return {"token": v["access"], "org": (v.get("metadata") or {}).get("orgID")}
    for c in creds:
        v = c.get("value") or {}
        if v.get("access"):
            return {"token": v["access"], "org": (v.get("metadata") or {}).get("orgID")}
    return None


def resolve(cfg: Config, session_id: str | None = None) -> LLMBackend:
    """根据配置返回实际使用的 LLM 后端。"""
    provider = (cfg.llm.provider or "").strip()
    if provider:
        provs, _ = providers_mod.load(cfg)
        info = providers_mod.resolve(provs, provider, cfg.llm.model or None, cfg.llm.variant or None)
        return LLMBackend(
            info["base_url"],
            info["api_key"],
            info["model"],
            dict(info.get("headers") or {}),
            label=f"provider:{provider}",
            extra_body=dict(info.get("body") or {}),
        )

    backend = (cfg.llm.backend or "").strip().lower()
    if backend.startswith("opencode"):
        cred = _pick_credential("opencode")
        if not cred:
            raise RuntimeError(
                "读不到 OpenCode 凭证。请先运行 `opencode auth login` 登录 OpenCode/Go。"
            )
        base = GO_BASE.get(backend, GO_BASE["opencode-go"])
        headers = {
            "x-opencode-session": session_id or f"ctfcode-{uuid.uuid4().hex[:16]}",
            "User-Agent": "ctfcode-agent/0.1",
        }
        if cred.get("org"):
            headers["x-opencode-org-id"] = cred["org"]
        return LLMBackend(base, cred["token"], cfg.llm.model, headers, label=backend)

    return LLMBackend(
        cfg.llm.base_url,
        cfg.llm.api_key,
        cfg.llm.model,
        dict(cfg.llm.headers or {}),
        label="custom",
    )


def is_ready(cfg: Config) -> bool:
    """LLM 是否已具备可用配置（用于 UI 提示）。"""
    if (cfg.llm.provider or "").strip():
        try:
            provs, _ = providers_mod.load(cfg)
            providers_mod.resolve(provs, cfg.llm.provider.strip(),
                                  cfg.llm.model or None, cfg.llm.variant or None)
            return True
        except Exception:
            return False
    if (cfg.llm.backend or "").strip().lower().startswith("opencode"):
        return True
    return bool(cfg.llm.api_key) and not cfg.llm.api_key.startswith("sk-替换")


def list_models(cfg: Config, session_id: str | None = None) -> list[str]:
    """列出当前后端可用的模型 ID。"""
    backend = resolve(cfg, session_id)
    if backend.label.startswith("opencode"):
        url = backend.base_url.replace("/openai/v1", "/v1").rstrip("/") + "/models"
    else:
        url = backend.base_url.rstrip("/") + "/models"
    headers = dict(backend.headers)
    if backend.api_key:
        headers["Authorization"] = f"Bearer {backend.api_key}"
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    data = d.get("data", d) if isinstance(d, dict) else d
    return [m["id"] for m in data if isinstance(m, dict) and "id" in m]

