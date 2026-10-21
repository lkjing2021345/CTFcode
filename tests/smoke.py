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


def test_sanitize_tool_history() -> None:
    from ctfcode.config import load_config
    from ctfcode.llm import AgentSession
    from ctfcode.tools import ToolRunner

    s = AgentSession(load_config(None), ToolRunner(tempfile.mkdtemp()))
    s.messages += [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "a1", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
            {"id": "a2", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "a1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]
    s._sanitize()
    tools = [m for m in s.messages if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tools] == ["a1", "a2"], tools
    assert tools[1]["content"] == "(aborted)"


def test_providers() -> None:
    import json

    from ctfcode.providers import list_models, resolve, strip_jsonc

    text = """
    {
      // comment
      "providers": {
        "p": {
          "settings": {"baseURL": "http://x"},
          "models": {
            "m": {"body": {"a": 1}, "variants": [{"id": "v", "body": {"a": 2}}]},
          },
        },
      },
    }
    """
    data = json.loads(strip_jsonc(text))
    provs = data["providers"]
    assert list_models(provs)[0]["label"] == "p/m"
    info = resolve(provs, "p", "m", "v")
    assert info["base_url"] == "http://x"
    assert info["body"] == {"a": 2}
    assert resolve(provs, "p", "m")["body"] == {"a": 1}


def test_provider_backend() -> None:
    import tempfile

    from ctfcode.config import load_config
    from ctfcode.llm_backend import is_ready, resolve

    path = os.path.join(tempfile.mkdtemp(), "prov.jsonc")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            '{"providers":{"p":{"settings":{"baseURL":"http://127.0.0.1:1/v1"},'
            '"models":{"m":{"body":{"enable_thinking":false}}}}}}'
        )
    cfg = load_config(None)
    cfg.providers_file = path
    cfg.llm.provider = "p"
    cfg.llm.model = "m"
    cfg.llm.backend = ""
    assert is_ready(cfg)
    b = resolve(cfg)
    assert b.label == "provider:p" and b.extra_body == {"enable_thinking": False}


def test_anthropic_converters() -> None:
    from ctfcode.anthropic_backend import convert_messages, convert_tools

    tools = convert_tools([{
        "type": "function",
        "function": {"name": "bash", "description": "d",
                     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}},
    }])
    assert tools[0]["name"] == "bash" and "input_schema" in tools[0]

    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function",
             "function": {"name": "bash", "arguments": '{"command":"ls"}'}},
        ]},
        {"role": "tool", "tool_call_id": "t1", "content": "ok"},
    ]
    system, conv = convert_messages(msgs)
    assert system == "sys"
    assert conv[0]["content"][1]["type"] == "image"
    assert conv[0]["content"][1]["source"]["media_type"] == "image/png"
    assert conv[1]["content"][0]["type"] == "tool_use"
    assert conv[1]["content"][0]["input"] == {"command": "ls"}
    assert conv[2]["content"][0]["type"] == "tool_result"


def test_anthropic_backend_resolve() -> None:
    from ctfcode.config import load_config
    from ctfcode.llm_backend import resolve

    cfg = load_config(None)
    cfg.llm.backend = "anthropic"
    cfg.llm.model = "claude-sonnet-4-5"
    cfg.llm.api_key = "sk-ant-test"
    b = resolve(cfg)
    assert b.label == "anthropic"
    assert b.base_url == "https://api.anthropic.com"
    assert b.model == "claude-sonnet-4-5"


def test_anthropic_stream_events() -> None:
    import asyncio
    from types import SimpleNamespace as NS

    from ctfcode.anthropic_backend import stream_chat

    events = [
        NS(type="content_block_start", index=0, content_block=NS(type="thinking")),
        NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking="想")),
        NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking="一下")),
        NS(type="content_block_start", index=1, content_block=NS(type="text")),
        NS(type="content_block_delta", index=1, delta=NS(type="text_delta", text="你好")),
        NS(type="content_block_start", index=2, content_block=NS(type="tool_use", id="t1", name="bash")),
        NS(type="content_block_delta", index=2,
           delta=NS(type="input_json_delta", partial_json='{"command":"ls"}')),
    ]

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            async def gen():
                for e in events:
                    yield e

            return gen()

    class Messages:
        def stream(self, **kw):
            return Stream()

    fake = NS(messages=Messages())
    seen: list[str] = []

    def emit(kind, data):
        seen.append(kind)

    content, reasoning, tool_acc = asyncio.run(
        stream_chat(fake, model="m", system="s", messages=[], tools=[], emit=emit, thinking=True)
    )
    assert content == "你好"
    assert reasoning == "想一下"
    assert tool_acc[2]["name"] == "bash" and tool_acc[2]["args"] == '{"command":"ls"}'
    assert "reasoning_start" in seen and "assistant_start" in seen


async def _tui_mouse_scroll() -> None:
    from textual import events
    from textual.containers import VerticalScroll

    from ctfcode.config import load_config
    from ctfcode.tui import CTFApp

    cfg = load_config(None)
    cfg.mcp = {}
    cfg.ui["resume"] = False
    cfg.ui["sessions_dir"] = tempfile.mkdtemp(prefix="ctfcode-mouse-")
    app = CTFApp(cfg)
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        for i in range(120):
            app._log((f"line {i}", ""))
        await pilot.pause()
        await pilot.pause()
        log = app.query_one("#log", VerticalScroll)
        assert log.max_scroll_y > 0
        # 指针停在输入框（非日志区）时，App 级兜底也要滚动日志
        before = log.scroll_offset.y
        app.screen._forward_event(events.MouseScrollUp(
            widget=None, x=5, y=19, delta_x=0, delta_y=-1,
            button=0, shift=False, meta=False, ctrl=False,
        ))
        await pilot.pause()
        assert log.scroll_offset.y < before, (before, log.scroll_offset.y)


def test_mouse_scroll() -> None:
    asyncio.run(_tui_mouse_scroll())


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
        ("sanitize-tool-history", test_sanitize_tool_history),
        ("providers", test_providers),
        ("provider-backend", test_provider_backend),
        ("anthropic-converters", test_anthropic_converters),
        ("anthropic-backend", test_anthropic_backend_resolve),
        ("anthropic-stream", test_anthropic_stream_events),
        ("mouse-scroll", test_mouse_scroll),
    ]:
        check(name, fn)
    if failures:
        print(f"\n{len(failures)} failed")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
