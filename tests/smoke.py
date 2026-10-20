#!/usr/bin/env python3
"""最小冒烟测试：不依赖真实 LLM、网络、剪贴板内容。

运行：  ./venv/bin/python tests/smoke.py
失败会以非 0 退出。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

failures: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"{name}: {e}")
        print(f"  FAIL {name}: {e}")


def test_imports() -> None:
    from ctfcode import clipboard, config, llm_backend, skills, tools  # noqa: F401

    assert len(skills.names()) >= 10, "技能数量异常"


def test_skills() -> None:
    from ctfcode import skills

    body = skills.handle("recon")
    assert "nmap" in body and "gobuster" in body
    assert "未知技能" in skills.handle("__none__")


def test_config() -> None:
    from ctfcode.config import load_config

    cfg = load_config(None)
    assert cfg is not None
    assert hasattr(cfg, "llm") and hasattr(cfg, "ui")


def test_tools() -> None:
    from ctfcode.tools import ToolRunner, dispatch

    with tempfile.TemporaryDirectory() as d:
        r = ToolRunner(d)
        out = dispatch(r, "bash", {"command": "echo smoke_ok"})
        assert "smoke_ok" in out, out
        out = dispatch(r, "read_file", {"path": "../../etc/passwd"})
        assert "越界" in out or "error" in out.lower()


def test_container_parse() -> None:
    from ctfcode.gzctf import GZCTFClient

    info = GZCTFClient.parse_instance({"instanceEntry": "nc 1.2.3.4 1337"})
    assert info["entry"] == "nc 1.2.3.4 1337"


def test_mcp_message_shapes() -> None:
    from ctfcode.mcp_client import MCPManager

    m = MCPManager()
    assert m.schemas() == []
    assert m.summary()  # 空配置也有可读信息


async def _tui() -> None:
    from textual.containers import VerticalScroll

    from ctfcode.config import load_config
    from ctfcode.tui import CTFApp, LeaderScreen

    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = tempfile.mkdtemp(prefix="ctfcode-smoke-")
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        assert app.query_one("#log", VerticalScroll) is not None
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert isinstance(app.screen, LeaderScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, LeaderScreen)


def test_tui() -> None:
    asyncio.run(_tui())


def main() -> int:
    print("smoke tests:")
    for name, fn in [
        ("imports", test_imports),
        ("skills", test_skills),
        ("config", test_config),
        ("tools", test_tools),
        ("container-parse", test_container_parse),
        ("mcp-shapes", test_mcp_message_shapes),
        ("tui-mount+leader", test_tui),
    ]:
        check(name, fn)
    if failures:
        print(f"\n{len(failures)} failed")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
