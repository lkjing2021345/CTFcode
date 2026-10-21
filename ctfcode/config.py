"""配置加载：优先读 config.yaml，其次环境变量。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    backend: str = ""
    provider: str = ""
    variant: str = ""
    headers: dict = field(default_factory=dict)


@dataclass
class GZCTFConfig:
    url: str = ""
    token: str = ""
    user: str = ""
    password: str = ""


@dataclass
class Config:
    llm: LLMConfig
    gzctf: GZCTFConfig = field(default_factory=GZCTFConfig)
    encrypt_password: bool = False
    rsa_padding: str = "oaep"
    max_steps: int = 30
    bash_timeout: int = 60
    workroot: str = os.path.expanduser("~/CTF/WriteUp")
    scratch: str = os.path.expanduser("~/.cache/gzctf-agent/scratch")
    mcp: dict = field(default_factory=dict)
    ui: dict = field(default_factory=dict)
    providers_file: str = ""
    source: str = ""


def load_config(path: str | None = None) -> Config:
    data: dict = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    elif os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    llm = data.get("llm", {}) or {}
    llm_cfg = LLMConfig(
        base_url=os.environ.get("LLM_BASE_URL", llm.get("base_url", "https://api.deepseek.com/v1")),
        api_key=os.environ.get("LLM_API_KEY", llm.get("api_key", "")),
        model=os.environ.get("LLM_MODEL", llm.get("model", "deepseek-chat")),
        backend=os.environ.get("LLM_BACKEND", llm.get("backend", "")),
        provider=os.environ.get("LLM_PROVIDER", llm.get("provider", "")),
        variant=os.environ.get("LLM_VARIANT", llm.get("variant", "")),
        headers=llm.get("headers", {}) or {},
    )

    g = data.get("gzctf", {}) or {}
    gzctf_cfg = GZCTFConfig(
        url=os.environ.get("GZCTF_URL", g.get("url", "")),
        token=os.environ.get("GZCTF_TOKEN", g.get("token", "")),
        user=os.environ.get("GZCTF_USER", g.get("user", "")),
        password=os.environ.get("GZCTF_PASSWORD", g.get("password", "")),
    )

    return Config(
        llm=llm_cfg,
        gzctf=gzctf_cfg,
        encrypt_password=bool(data.get("encrypt_password", False)),
        rsa_padding=data.get("rsa_padding", "oaep"),
        max_steps=int(data.get("max_steps", 30)),
        bash_timeout=int(data.get("bash_timeout", 60)),
        workroot=os.path.expanduser(data.get("workroot", "~/CTF/WriteUp")),
        scratch=os.path.expanduser(data.get("scratch", "~/.cache/gzctf-agent/scratch")),
        mcp=data.get("mcp", {}) or {},
        ui=data.get("ui", {}) or {},
        providers_file=os.path.expanduser(data.get("providers_file", "")),
        source=(path if path and os.path.exists(path) else ("config.yaml" if os.path.exists("config.yaml") else "(未找到配置，使用默认值)")),
    )
