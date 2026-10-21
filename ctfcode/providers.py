"""自定义提供商管理：读取 opencode 风格的 JSONC 提供商配置。

文件格式与 `~/.config/opencode/opencode.jsonc` 的 `providers` 段兼容：
    {
      "providers": {
        "qwen": {
          "name": "Qwen",
          "settings": {"baseURL": "http://127.0.0.1:8080/v1"},
          "models": {
            "qwen38": {
              "name": "Qwen3.8-27B",
              "body": {"enable_thinking": true},
              "variants": [{"id": "nothink", "body": {"enable_thinking": false}}]
            }
          }
        }
      }
    }

查找顺序：
1. config.yaml 的 `providers_file`
2. 项目目录下的 `providers.jsonc`
3. `~/.config/opencode/opencode.jsonc`
"""
from __future__ import annotations

import json
import os
import re

from .config import Config

_AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def strip_jsonc(text: str) -> str:
    """去掉 // 与 /* */ 注释、尾逗号（保留字符串内容）。"""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def find_file(cfg: Config) -> str | None:
    candidates = []
    if getattr(cfg, "providers_file", ""):
        candidates.append(os.path.expanduser(cfg.providers_file))
    candidates += [
        os.path.join(_AGENT_DIR, "providers.jsonc"),
        os.path.expanduser("~/.config/opencode/opencode.jsonc"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def load(cfg: Config) -> tuple[dict, str | None]:
    """返回 (providers 字典, 文件路径)。"""
    path = find_file(cfg)
    if not path:
        return {}, None
    try:
        data = json.loads(strip_jsonc(open(path, encoding="utf-8").read()))
    except Exception:
        return {}, path
    provs = data.get("providers", {}) if isinstance(data, dict) else {}
    return (provs if isinstance(provs, dict) else {}), path


def list_models(providers: dict) -> list[dict]:
    out: list[dict] = []
    for pid, p in (providers or {}).items():
        models = (p or {}).get("models") or {}
        for mid, m in models.items():
            m = m or {}
            out.append({
                "provider": pid,
                "model": mid,
                "name": m.get("name") or mid,
                "label": f"{pid}/{mid}",
                "variants": [v.get("id") for v in (m.get("variants") or []) if v.get("id")],
            })
    return out


def resolve(providers: dict, provider_id: str, model_id: str | None = None,
            variant: str | None = None) -> dict:
    p = (providers or {}).get(provider_id)
    if not isinstance(p, dict):
        raise KeyError(f"未知提供商：{provider_id}")
    models = p.get("models") or {}
    mid = model_id or next(iter(models), None)
    if not mid or mid not in models:
        raise KeyError(f"提供商 {provider_id} 下没有模型 {model_id}")
    m = models[mid] or {}
    body = dict(m.get("body") or {})
    if variant:
        for v in m.get("variants") or []:
            if v.get("id") == variant:
                body.update(v.get("body") or {})
                break
    settings = p.get("settings") or {}
    base = settings.get("baseURL") or settings.get("baseUrl")
    if not base:
        raise KeyError(f"提供商 {provider_id} 缺少 settings.baseURL")
    key = (
        settings.get("apiKey")
        or os.environ.get(f"CTFCODE_PROVIDER_{provider_id.upper()}_KEY")
        or "sk-noauth"
    )
    return {
        "base_url": base,
        "model": mid,
        "name": m.get("name") or mid,
        "body": body,
        "api_key": key,
        "headers": dict(settings.get("headers") or {}),
    }
