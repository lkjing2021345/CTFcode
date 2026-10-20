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


async def _tui_extra() -> None:
    from ctfcode.config import load_config
    from ctfcode.tui import CTFApp, ConfirmModal

    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = tempfile.mkdtemp(prefix="ctfcode-smoke2-")
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        sysmsg = app.session.messages[0]
        app.session.messages = [sysmsg,
                                {"role": "user", "content": "hi"},
                                {"role": "assistant", "content": "yo"}]
        app._command("/undo")
        await pilot.pause()
        assert len(app.session.messages) == 1, app.session.messages
        assert app.query_one("#prompt").value == "hi"
        app._command("/redo")
        await pilot.pause()
        assert len(app.session.messages) == 3
        got: list[bool] = []
        app.push_screen(ConfirmModal("flag{x}", "reason"), lambda v: got.append(v))
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert got == [True], got


def test_tui_undo_redo_confirm() -> None:
    asyncio.run(_tui_extra())


def test_session_store() -> None:
    from ctfcode.sessions import SessionStore

    store = SessionStore(tempfile.mkdtemp(prefix="ctfcode-sess-"))
    sid = store.new_id()
    store.save({"id": sid, "title": "demo", "messages": [{"role": "system", "content": "x"}]})
    assert store.load(sid)["title"] == "demo"
    assert any(x["id"] == sid for x in store.list())


def test_writeup_fallback() -> None:
    from ctfcode import writeup

    md = writeup._fallback(
        {"title": "T", "category": "Misc", "cid": 1, "description": "d"},
        ["[user] hi", "[flag] flag{a}"],
        "flag{a}",
    )
    assert "flag{a}" in md and "T" in md


def test_clipboard_dataurl() -> None:
    from PIL import Image

    from ctfcode.clipboard import image_data_url, is_image, is_video

    path = os.path.join(tempfile.mkdtemp(), "t.png")
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path)
    url = image_data_url(path)
    assert url.startswith("data:image/png;base64,")
    assert is_image(path) and not is_video(path)


async def _tui_find_sessions() -> None:
    from ctfcode.config import load_config
    from ctfcode.sessions import SessionStore
    from ctfcode.tui import CTFApp

    d = tempfile.mkdtemp(prefix="ctfcode-sess2-")
    store = SessionStore(d)
    a, b = store.new_id(), store.new_id()
    store.save({"id": a, "title": "A", "messages": [{"role": "system", "content": "x"}],
                "transcript": ["[user] A"]})
    store.save({"id": b, "title": "B", "messages": [{"role": "system", "content": "x"}],
                "transcript": ["[user] B"]})
    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = d
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app._command("/sessions")
        await pilot.pause()
        assert len(app._session_list) == 2, app._session_list
        app._command("/sessions 1")
        await pilot.pause()
        assert app.sess_id == app._session_list[1]["id"]
        app.session.transcript = ["[user] hello flag", "[assistant] none"]
        app._command("/find flag")
        await pilot.pause()
        app._command("/find zzzz-not-found")
        await pilot.pause()


def test_find_and_session_switch() -> None:
    asyncio.run(_tui_find_sessions())


async def _tui_modal_focus() -> None:
    from ctfcode.config import load_config
    from ctfcode.tui import CTFApp, ConfirmModal

    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = tempfile.mkdtemp(prefix="ctfcode-modal-")
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app.push_screen(ConfirmModal("flag{x}", "r"), app._on_confirm)
        await pilot.pause()
        assert app.active_bindings.get("ctrl+q") is not None, "模态内 ctrl+q 未绑定"
        await pilot.press("n")
        await pilot.pause()
        await pilot.pause()
        assert type(app.focused).__name__ == "Input", app.focused


def test_modal_ctrl_q_and_focus() -> None:
    asyncio.run(_tui_modal_focus())


def test_friendly_errors() -> None:
    from ctfcode.errors import friendly

    assert "文件不存在" in friendly(FileNotFoundError(2, "no such file", "a.txt"))
    assert "超时" in friendly(TimeoutError())
    assert "ValueError" in friendly(ValueError("bad"))


def test_missing_config_source() -> None:
    from ctfcode.config import load_config

    old = os.getcwd()
    try:
        os.chdir(tempfile.mkdtemp())
        cfg = load_config(None)
        assert "未找到" in cfg.source, cfg.source
    finally:
        os.chdir(old)


def test_mcp_down() -> None:
    from ctfcode.mcp_client import MCPManager

    async def run() -> None:
        m = MCPManager()
        await m.connect_all({"dead": {"transport": "sse", "url": "http://127.0.0.1:1", "timeout": 2}})
        assert "dead" in m.errors, m.errors
        assert not m.schemas()
        await m.close()

    asyncio.run(run())


async def _export_empty() -> None:
    from ctfcode.config import load_config
    from ctfcode.tui import CTFApp

    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = tempfile.mkdtemp(prefix="ctfcode-exp-")
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app.session.transcript = []
        out = os.path.join(tempfile.mkdtemp(), "empty.md")
        app._command(f"/export {out}")
        await pilot.pause()
        text = open(out, encoding="utf-8").read()
        assert "暂无记录" in text, text


def test_export_empty_session() -> None:
    asyncio.run(_export_empty())


async def _picker() -> None:
    from ctfcode.config import load_config
    from ctfcode.sessions import SessionStore
    from ctfcode.tui import CTFApp, SessionPicker

    d = tempfile.mkdtemp(prefix="ctfcode-pick-")
    store = SessionStore(d)
    ids = [store.new_id(), store.new_id()]
    for i, sid in enumerate(ids):
        store.save({"id": sid, "title": f"S{i}", "messages": [{"role": "system", "content": "x"}],
                    "transcript": [f"[user] {i}"]})
    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = d
    app = CTFApp(cfg)
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        app._pick_session()
        await pilot.pause()
        assert isinstance(app.screen, SessionPicker)
        for ch in "S1":
            await pilot.press(ch)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, SessionPicker)
        assert app.sess_title == "S1", app.sess_title


def test_session_picker() -> None:
    asyncio.run(_picker())


def test_qemu_helpers() -> None:
    import socket
    import types

    from scripts.qemu_target import _parse_ports, _probe

    ns = types.SimpleNamespace(low="1-3", ports="22,80")
    assert _parse_ports(ns) == [1, 2, 3, 22, 80], _parse_ports(ns)

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    assert _probe(port, timeout=1) is True
    srv.close()
    assert _probe(port, timeout=0.3) is False


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
        ("tui-undo-redo-confirm", test_tui_undo_redo_confirm),
        ("session-store", test_session_store),
        ("writeup-fallback", test_writeup_fallback),
        ("clipboard-dataurl", test_clipboard_dataurl),
        ("find+session-switch", test_find_and_session_switch),
        ("modal-ctrl-q+focus", test_modal_ctrl_q_and_focus),
        ("friendly-errors", test_friendly_errors),
        ("missing-config", test_missing_config_source),
        ("mcp-down", test_mcp_down),
        ("export-empty", test_export_empty_session),
        ("session-picker", test_session_picker),
        ("qemu-helpers", test_qemu_helpers),
    ]:
        check(name, fn)
    if failures:
        print(f"\n{len(failures)} failed")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
