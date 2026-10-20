"""CTFcode 的终端前端（终端交互风格）。

- 多轮对话 + 工具调用可视化
- Ctrl+V 粘贴：优先图片 → 文件 → 文本；视频自动抽帧
- 斜杠命令：/open /game /challenge /solve /submit /writeup ...
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import threading
import uuid

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Header, Input, Static
from textual.widgets._collapsible import CollapsibleTitle

from . import writeup as writeup_mod
from .clipboard import extract_frames, grab_files, grab_image, grab_text, is_image, is_video
from .config import Config, load_config
from .container import ContainerManager
from .gzctf import Challenge, GZCTFClient, GZCTFError
from .llm import AgentSession
from .llm_backend import is_ready as llm_ready
from .mcp_client import MCPManager
from .sessions import SessionStore, fmt_time
from .tools import ToolRunner

CACHE = os.path.expanduser("~/.cache/gzctf-agent")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# 图标预设：plain 到处都能显示；nerd 用 Nerd Font 字形（需终端字体为 *Nerd Font*）
ICON_SETS = {
    "plain": {"collapsed": "▸", "expanded": "▾", "user": "› ", "assistant": "● ", "connector": "└ "},
    "nerd": {"collapsed": "\uf054", "expanded": "\uf078", "user": "\uf105 ", "assistant": "● ", "connector": "└ "},
}


def _strip_astral(s: str) -> str:
    """去掉 BMP 之外(字形常缺失)的字符/emoji，避免终端显示成方块。"""
    return "".join(ch for ch in s if ord(ch) <= 0xFFFF)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:60]


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "confirm", "确认", show=True),
        Binding("enter", "confirm", "确认", show=False),
        Binding("n", "cancel", "忽略", show=True),
        Binding("escape", "cancel", "忽略", show=False),
    ]

    def __init__(self, flag: str, reason: str = ""):
        super().__init__()
        self.flag = flag
        self.reason = reason
        self._done = False

    def compose(self) -> ComposeResult:
        yield Grid(
            Static(f"发现候选 flag：\n\n[bold magenta]{self.flag}[/]\n\n{self.reason}\n\n确认提交吗？",
                   id="confirm-msg"),
            Horizontal(
                Button("确认提交", variant="success", id="yes"),
                Button("忽略", variant="error", id="no"),
                id="confirm-btns",
            ),
            Static("按 Y / Enter 确认      N / Esc 忽略", id="confirm-hint"),
            id="confirm-box",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#yes", Button).focus()
        except Exception:
            pass

    def _finish(self, ok: bool) -> None:
        if self._done:
            return
        self._done = True
        self.dismiss(ok)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._finish(event.button.id == "yes")

    def action_confirm(self) -> None:
        self._finish(True)

    def action_cancel(self) -> None:
        self._finish(False)


class LeaderScreen(ModalScreen[str | None]):
    """Ctrl+X 之后的一键操作面板（类似编辑器 leader）。"""

    BINDINGS = [
        Binding("n", "pick('n')", "新会话", show=True),
        Binding("l", "pick('l')", "会话列表", show=True),
        Binding("m", "pick('m')", "模型", show=True),
        Binding("c", "pick('c')", "MCP", show=True),
        Binding("u", "pick('u')", "撤销", show=True),
        Binding("r", "pick('r')", "恢复", show=True),
        Binding("h", "pick('h')", "帮助", show=True),
        Binding("escape", "pick('')", "取消", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]Leader[/b]  (Ctrl+X)\n\n"
            "  [b]n[/]  新建会话        [b]l[/]  会话列表        [b]m[/]  模型\n"
            "  [b]c[/]  MCP             [b]u[/]  撤销            [b]r[/]  恢复\n"
            "  [b]h[/]  帮助            [b]Esc[/] 取消",
            id="leader-box",
        )

    def action_pick(self, key: str) -> None:
        self.dismiss(key or None)


class CTFApp(App):
    TITLE = "CTFcode"
    CSS = """
    #log {
        height: 1fr;
        padding: 0 1;
        border: none;
        border-left: solid $panel;
        scrollbar-size-vertical: 1;
        scrollbar-background: $surface;
        scrollbar-color: $panel;
        scrollbar-color-hover: $accent;
        scrollbar-color-active: $accent;
    }
    #log Static { width: 100%; }

    .thinking, .tool {
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        height: auto;
    }
    .thinking > CollapsibleTitle, .tool > CollapsibleTitle {
        background: transparent;
        padding: 0;
        color: $text-muted;
    }
    .thinking > CollapsibleTitle:hover, .tool > CollapsibleTitle:hover {
        background: transparent;
        color: $foreground;
    }
    .thinking > Contents, .tool > Contents {
        padding: 0 0 0 2;
    }
    .reasoning-body { color: $text-disabled; }
    .tool-body { color: $text; }

    #status { height: 1; padding: 0 2; color: $accent; }
    #attach { height: auto; padding: 0 1; color: $text-muted; }

    #prompt, #prompt:focus {
        dock: bottom;
        height: 1;
        padding: 0 1;
        border: none;
        background: $surface;
    }

    ConfirmModal { align: center middle; }
    #confirm-box { width: 74; height: auto; border: thick $accent; background: $surface; padding: 1 2; }
    #confirm-msg { height: auto; }
    #confirm-hint { height: auto; color: $text-muted; margin-top: 1; }
    #confirm-btns { height: auto; align: center middle; }
    LeaderScreen { align: center middle; }
    #leader-box { width: 64; height: auto; border: thick $accent; background: $surface; padding: 1 2; }
    """
    BINDINGS = [
        Binding("ctrl+v", "paste", "粘贴", priority=True),
        Binding("ctrl+w", "writeup", "WriteUp", priority=True),
        Binding("ctrl+o", "toggle_thinking", "展开/折叠思考"),
        Binding("ctrl+x", "leader", "Leader", show=False, priority=True),
        Binding("escape", "abort", "终止", show=False),
        Binding("pageup", "scroll_log('up')", "上翻", show=True, priority=True),
        Binding("pagedown", "scroll_log('down')", "下翻", show=True, priority=True),
        Binding("ctrl+home", "scroll_log('top')", "顶部", show=False),
        Binding("ctrl+end", "scroll_log('bottom')", "底部", show=False),
        Binding("shift+up", "scroll_log('up')", show=False),
        Binding("shift+down", "scroll_log('down')", show=False),
        Binding("ctrl+l", "clear_log", "清屏"),
        Binding("ctrl+q", "quit", "退出"),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.client: GZCTFClient | None = None
        self.container: ContainerManager | None = None
        self.gid: int | None = None
        self.challenge: Challenge | None = None
        self.detail: dict = {}
        self.workdir: str | None = None
        self.challenges: list[Challenge] = []
        self.attachments: list[str] = []
        self.model_list: list[str] = []
        self.session_id = "ctfcode-" + uuid.uuid4().hex[:16]
        self._status_msg = ""
        self._spin_i = 0
        self._last_tool = None
        self._live_reasoning = None
        self._live_assistant = None
        self.icons = ICON_SETS.get((cfg.ui.get("icons") or "plain").lower(), ICON_SETS["plain"])
        self.mcp: MCPManager | None = None
        # 会话持久化
        self.store = SessionStore(cfg.ui.get("sessions_dir") or "~/.local/share/gzctf-agent/sessions")
        self.sess_id = self.store.new_id()
        self.sess_title = ""
        self.sess_created = None
        self._session_list: list[dict] = []
        self._redo: list = []
        self._abort = threading.Event()
        self._worker = None
        self._agent_busy = False
        self._queue: list[tuple[str, list[str]]] = []
        os.makedirs(cfg.scratch, exist_ok=True)
        self.runner = ToolRunner(cfg.scratch, cfg.bash_timeout)
        self.session = AgentSession(cfg, self.runner, session_id=self.session_id)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # 模态框（如确认提交）打开时，不要让 priority 绑定穿透过去
        if getattr(self.screen, "is_modal", False) and action in {
            "paste", "writeup", "scroll_log", "toggle_thinking", "clear_log"
        }:
            return False
        return True

    # ---------- UI ----------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="log")
        yield Static("", id="status")
        yield Static("", id="attach")
        yield Input(placeholder="输入消息，或 / 开头执行命令（/help 查看）", id="prompt")

    def on_mount(self) -> None:
        self.query_one("#log", VerticalScroll).can_focus = False
        self.query_one("#prompt", Input).focus()
        self.set_interval(0.12, self._tick)
        self._log(("CTFcode 已就绪。", "bold"))
        self._log(("用 /open 连接站点，/help 看命令，Ctrl+V 粘贴图片/视频/文本，Ctrl+O 展开思考。", "dim"))
        if not llm_ready(self.cfg):
            self._log(("! 未配置 LLM：请在 config.yaml 设置 llm.api_key，或设 llm.backend: opencode-go 复用 OpenCode 登录。",
                       "bold yellow"))
        else:
            kind = self.cfg.llm.backend or "custom"
            self._log((f"LLM 后端：{kind} / {self.cfg.llm.model}", "dim"))
        if self.cfg.mcp:
            self.run_worker(self._init_mcp())
        self._resume_latest()
        self._refresh_header()
        self._log((f"配置：{self.cfg.source}", "dim"))
        self._log((f"LLM：{self.cfg.llm.backend or 'custom'} / {self.cfg.llm.model}", "dim"))

    # ---------- 会话 ----------
    def _refresh_header(self) -> None:
        label = self.sess_title or "(新会话)"
        self.sub_title = f"{label}  ·  {self.sess_id}"

    def _persist(self) -> None:
        try:
            self.store.save({
                "id": self.sess_id,
                "title": self.sess_title,
                "created": self.sess_created or 0,
                "model": self.cfg.llm.model,
                "workdir": self.workdir,
                "messages": self.session.messages,
                "transcript": self.session.transcript,
            })
        except Exception:
            pass

    def _resume_latest(self) -> None:
        if self.cfg.ui.get("resume", True) is False:
            return
        items = self.store.list()
        if items:
            data = self.store.load(items[0]["id"])
            if data:
                self._restore_session(data)

    def _restore_session(self, data: dict) -> None:
        self.sess_id = data.get("id") or self.store.new_id()
        self.sess_title = data.get("title", "") or ""
        self.sess_created = data.get("created") or 0
        self.session = AgentSession(self.cfg, self.runner, session_id=self.session_id)
        self.session.mcp = self.mcp
        msgs = data.get("messages") or []
        if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
            self.session.messages = [self.session.messages[0]] + msgs[1:]
        elif msgs:
            self.session.messages = [self.session.messages[0]] + msgs
        self.session.transcript = data.get("transcript") or []
        self._redo = []
        # 重放简要历史
        self.query_one("#log", VerticalScroll).remove_children()
        for line in self.session.transcript[-80:]:
            self._log((line[:500], "dim"))
        self._refresh_header()
        self._log((f"已恢复会话 {self.sess_id}（{len(self.session.messages) - 1} 条消息）", "bold green"))

    def _new_session(self) -> None:
        self._persist()
        self.session.reset()
        self.sess_id = self.store.new_id()
        self.sess_title = ""
        self.sess_created = 0
        self._redo = []
        self.query_one("#log", VerticalScroll).remove_children()
        self._refresh_header()
        self._log(("已新建会话。", "bold green"))

    def _title_from(self, text: str) -> None:
        if not self.sess_title:
            self.sess_title = text.strip().replace("\n", " ")[:40]
            self._refresh_header()

    async def _init_mcp(self) -> None:
        self._log(("正在连接 MCP 服务器…", "dim"))
        self.mcp = MCPManager()
        await self.mcp.connect_all(self.cfg.mcp)
        self.session.mcp = self.mcp
        self._log(("MCP 服务器：", "bold"))
        self._log((self.mcp.summary(), "dim"))

    async def on_unmount(self) -> None:
        if self.mcp is not None:
            await self.mcp.close()

    # ---------- 日志 ----------
    def _mount(self, widget) -> None:
        try:
            log = self.query_one("#log", VerticalScroll)
        except Exception:
            return
        # 只有本来就在底部时才自动跟随；否则别打断用户翻看历史
        near_bottom = (log.max_scroll_y - log.scroll_offset.y) <= 3
        log.mount(widget)
        if near_bottom:
            self.call_after_refresh(log.scroll_end, animate=False)

    def action_scroll_log(self, direction: str = "down") -> None:
        log = self.query_one("#log", VerticalScroll)
        if direction == "up":
            log.scroll_page_up(animate=False)
        elif direction == "down":
            log.scroll_page_down(animate=False)
        elif direction == "top":
            log.scroll_home(animate=False)
        elif direction == "bottom":
            log.scroll_end(animate=False)

    def _log(self, *parts) -> None:
        self._mount(Static(Text.assemble(*parts)))

    def _make_clickable_no_focus(self, coll: Collapsible) -> None:
        def _no_focus() -> None:
            try:
                coll.query_one(CollapsibleTitle).can_focus = False
            except Exception:
                pass

        # 标题挂载后禁用聚焦：点击可展开，但键盘焦点仍留在输入框
        self.call_after_refresh(_no_focus)

    def _add_reasoning(self, text: str) -> None:
        body = Static(_strip_astral(text.strip()), markup=False, classes="reasoning-body")
        coll = Collapsible(body, title="思考过程", collapsed=True,
                           collapsed_symbol=self.icons["collapsed"],
                           expanded_symbol=self.icons["expanded"], classes="thinking")
        self._mount(coll)
        self._make_clickable_no_focus(coll)

    # ---------- 工具调用（默认折叠） ----------
    @staticmethod
    def _tool_title(name: str, args: dict) -> str:
        if name == "bash":
            cmd = str(args.get("command", "")).strip().replace("\n", " ")
            return f"bash: {cmd[:90]}"
        if name == "python":
            return "python: 脚本片段"
        if name == "skill":
            return f"skill: {args.get('name', '')}"
        if name in ("read_file", "write_file"):
            return f"{name}: {args.get('path', '')}"
        return f"{name}: {str(args)[:70]}"

    def _add_tool_call(self, name: str, args: dict) -> None:
        body = Static("运行中…", markup=False, classes="tool-body")
        coll = Collapsible(body, title=self._tool_title(name, args), collapsed=True,
                           collapsed_symbol=self.icons["collapsed"],
                           expanded_symbol=self.icons["expanded"], classes="tool")
        self._last_tool = coll
        self._mount(coll)
        self._make_clickable_no_focus(coll)

    def _fill_tool_result(self, result: str) -> None:
        coll = self._last_tool
        text = _strip_astral(result)
        lines = text.splitlines() or [""]
        body = "\n".join((self.icons["connector"] + ln) if i == 0 else ("  " + ln) for i, ln in enumerate(lines))
        if coll is None:
            self._log((body[:300], "dim"))
            return
        try:
            coll.query_one(Static).update(body)
        except Exception:
            pass

    # ---------- 运行状态指示 ----------
    def _set_status(self, msg: str) -> None:
        self._status_msg = msg
        self._render_status()

    def _render_status(self) -> None:
        try:
            w = self.query_one("#status", Static)
        except Exception:
            return
        if self._status_msg:
            frame = SPINNER[self._spin_i % len(SPINNER)]
            w.update(f"{frame} {self._status_msg}")
        else:
            w.update("")

    def _tick(self) -> None:
        self._spin_i += 1
        if self._status_msg:
            self._render_status()

    def on_collapsible_toggled(self, event) -> None:
        # 点开/收起思考后把焦点还给输入框，方便继续打字
        self.query_one("#prompt", Input).focus()

    def _refresh_attach(self) -> None:
        try:
            w = self.query_one("#attach", Static)
        except Exception:
            return
        parts = []
        if self.attachments:
            names = ", ".join(os.path.basename(p) for p in self.attachments)
            parts.append(f"待发送 {len(self.attachments)} 个附件：{names}")
        if self._queue:
            parts.append(f"排队 {len(self._queue)} 条")
        w.update("    ".join(parts))

    # ---------- 输入 ----------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        self.query_one("#prompt", Input).value = ""
        if not raw:
            return
        if raw.startswith("/"):
            self._command(raw)
        else:
            self._send_chat(raw)

    def _send_chat(self, text: str) -> None:
        imgs = list(self.attachments)
        self.attachments.clear()
        self._refresh_attach()
        if self._agent_busy:
            # 正在跑：排队，等当前回合结束再处理
            self._queue.append((text, imgs))
            self._log(("(排队) ", "yellow"), (_strip_astral(text)[:100], "dim"))
            self._refresh_attach()
            return
        self._queue.append((text, imgs))
        self._agent_busy = True
        self._worker = self.run_worker(self._run_loop(), exclusive=True)

    async def _run_loop(self) -> None:
        while self._queue:
            text, imgs = self._queue.pop(0)
            self._refresh_attach()
            self._agent_busy = True
            self._abort.clear()
            self.session.cancel_event = self._abort
            self._live_reasoning = None
            self._live_assistant = None
            self._title_from(text)
            self._log((self.icons["user"], "bold cyan"), (text, ""))
            if imgs:
                self._log(("     [图片] ", "dim"), (", ".join(os.path.basename(p) for p in imgs), "dim"))
                self.session.add_user_multimodal(text, imgs)
            else:
                self.session.add_user_text(text)
            self._set_status("思考中…")
            flag = None
            try:
                flag = await self.session.run(self._emit)
            except asyncio.CancelledError:
                self._log(("已终止（Esc），并清空排队。", "yellow"))
                self._queue.clear()
                self._refresh_attach()
                break
            except Exception as e:  # noqa: BLE001
                self._log(("! 出错：", "bold red"), (str(e), "red"))
                break
            finally:
                self._agent_busy = False
                self._set_status("")
                self._persist()
            if flag and not self._abort.is_set():
                self.push_screen(ConfirmModal(flag, self.session.flag_reason), self._on_confirm)
            if self._abort.is_set():
                self._queue.clear()
                self._refresh_attach()
                break
        self._agent_busy = False

    def action_leader(self) -> None:
        if getattr(self.screen, "is_modal", False):
            return
        self.push_screen(LeaderScreen(), self._on_leader)

    def _on_leader(self, key: str | None) -> None:
        if not key:
            return
        cmd = {
            "n": "/new", "l": "/sessions", "m": "/models", "c": "/mcp",
            "u": "/undo", "r": "/redo", "h": "/help",
        }.get(key)
        if cmd:
            self._command(cmd)

    def action_abort(self) -> None:
        if not self._agent_busy and not self._queue:
            return
        self._abort.set()
        self._log(("已请求终止…", "yellow"))
        if self._worker is not None:
            try:
                self._worker.cancel()
            except Exception:
                pass

    def _follow(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        if (log.max_scroll_y - log.scroll_offset.y) <= 3:
            log.scroll_end(animate=False)

    def _emit(self, kind: str, data) -> None:
        if self._abort.is_set():
            return
        if kind == "thinking":
            self._set_status("思考中…")
        elif kind == "reasoning_start":
            body = Static("", markup=False, classes="reasoning-body")
            coll = Collapsible(body, title="思考过程", collapsed=False,
                               collapsed_symbol="▸", expanded_symbol="▾", classes="thinking")
            self._mount(coll)
            self._make_clickable_no_focus(coll)
            self._live_reasoning = [coll, body, ""]
            self._set_status("思考中…")
        elif kind == "reasoning_delta":
            if self._live_reasoning:
                self._live_reasoning[2] += data
                self._live_reasoning[1].update(_strip_astral(self._live_reasoning[2]))
                self._follow()
        elif kind == "reasoning_end":
            if self._live_reasoning:
                self._live_reasoning[0].collapsed = True
                self._live_reasoning = None
        elif kind == "assistant_start":
            st = Static(Text(""), markup=False)
            self._mount(st)
            self._live_assistant = [st, ""]
        elif kind == "assistant_delta":
            if self._live_assistant:
                self._live_assistant[1] += data
                self._live_assistant[0].update(
                    Text.assemble((self.icons["assistant"], "bold green"), (_strip_astral(self._live_assistant[1]), "")))
                self._follow()
        elif kind == "assistant_end":
            self._live_assistant = None
        elif kind == "stream_fallback":
            self._log(("（该后端不支持流式，已回退一次性返回）", "dim"))
        elif kind == "reasoning":
            self._add_reasoning(data)
            self._set_status("思考中…")
        elif kind == "assistant":
            self._log((self.icons["assistant"], "bold green"), (_strip_astral(data), ""))
        elif kind == "tool_call":
            self._set_status(f"执行工具 {data['name']}…")
            self._add_tool_call(data["name"], data["args"])
        elif kind == "tool_result":
            self._set_status("处理结果…")
            self._fill_tool_result(data["result"])
        elif kind == "flag":
            self._set_status("整理候选 flag…")
            self._log(("候选 flag：", "bold magenta"), (data["flag"], "bold magenta"))

    # ---------- 命令 ----------
    def _command(self, raw: str) -> None:
        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ("/help", "/?"):
            self._help()
        elif cmd == "/open":
            self.run_worker(self._open(args))
        elif cmd == "/games":
            self.run_worker(self._games())
        elif cmd == "/game":
            self.run_worker(self._game(args))
        elif cmd == "/challenges":
            self._print_challenges()
        elif cmd == "/challenge":
            self.run_worker(self._challenge(args))
        elif cmd == "/start":
            self.run_worker(self._start_container())
        elif cmd == "/close":
            self.run_worker(self._close_container())
        elif cmd == "/solve":
            self._send_chat("请解这道题：先侦察附件，再逐步分析，解出后调用 submit_flag。")
        elif cmd == "/models":
            self.run_worker(self._models(args))
        elif cmd == "/model":
            if args:
                self._set_model(args[0])
            else:
                self._log((f"当前模型：{self.cfg.llm.model}（{self.cfg.llm.backend or 'custom'}）", "bold"))
        elif cmd == "/mcp":
            self._mcp_info()
        elif cmd == "/llm":
            self._llm_info()
        elif cmd == "/new":
            self._new_session()
        elif cmd == "/sessions":
            self._list_sessions()
        elif cmd == "/resume":
            self._resume_cmd(args)
        elif cmd == "/title":
            if args:
                self.sess_title = " ".join(args)
                self._refresh_header()
                self._persist()
            self._log((f"会话标题：{self.sess_title or '(无)'}", "dim"))
        elif cmd == "/undo":
            self._undo()
        elif cmd == "/redo":
            self._redo_cmd()
        elif cmd == "/submit":
            if args:
                self.run_worker(self._do_submit(" ".join(args)))
            else:
                self._log(("用法：/submit <flag>", "yellow"))
        elif cmd == "/writeup":
            self.run_worker(self._writeup())
        elif cmd == "/clear":
            self.session.reset()
            self.query_one("#log", VerticalScroll).remove_children()
            self._log(("已清空对话。", "dim"))
        elif cmd == "/quit":
            self.exit()
        else:
            self._log((f"未知命令 {cmd}，输入 /help 查看。", "red"))

    def _list_sessions(self) -> None:
        self._session_list = self.store.list()
        self._log((f"会话列表（{len(self._session_list)}）：", "bold"))
        for i, s in enumerate(self._session_list):
            mark = "  <- 当前" if s["id"] == self.sess_id else ""
            self._log((f"  [{i}] ", "cyan"),
                      (f"{s['title']}  {fmt_time(s['updated'])}  ({s['count']}条){mark}", ""))
        self._log(("用 /resume <序号|id> 切换。", "dim"))

    def _resume_cmd(self, args: list[str]) -> None:
        if not args:
            self._list_sessions()
            return
        key = args[0]
        sid = key
        if key.isdigit() and self._session_list and int(key) < len(self._session_list):
            sid = self._session_list[int(key)]["id"]
        data = self.store.load(sid)
        if not data:
            self._log((f"找不到会话 {sid}", "red"))
            return
        self._restore_session(data)

    def _undo(self) -> None:
        m = self.session.messages
        idx = None
        for i in range(len(m) - 1, 0, -1):
            if isinstance(m[i], dict) and m[i].get("role") == "user":
                idx = i
                break
        if idx is None:
            self._log(("没有可撤销的用户消息。", "yellow"))
            return
        removed = m[idx:]
        text = m[idx].get("content")
        self._redo.append(removed)
        self.session.messages = m[:idx]
        self._log(("已撤销最后一条用户消息（/redo 可恢复）。", "dim"))
        if isinstance(text, str):
            self.query_one("#prompt", Input).value = text
        self._persist()

    def _redo_cmd(self) -> None:
        if not self._redo:
            self._log(("没有可恢复的内容。", "yellow"))
            return
        self.session.messages.extend(self._redo.pop())
        self._log(("已恢复撤销的内容。", "dim"))
        self._persist()

    def _llm_info(self) -> None:
        from .llm_backend import is_ready, resolve

        self._log((f"cfg: backend={self.cfg.llm.backend!r} model={self.cfg.llm.model!r}", "dim"))
        self._log((f"配置来源：{self.cfg.source}", "dim"))
        if not is_ready(self.cfg):
            self._log(("未就绪：缺少 api_key，或 backend 不是 opencode-go", "red"))
            return
        try:
            b = resolve(self.cfg, self.session_id)
            self._log(("已解析后端：", "green"),
                      (f"{b.label} / {b.model} / token {len(b.api_key)} 字符", "green"))
        except Exception as e:  # noqa: BLE001
            self._log(("解析失败：", "red"), (str(e), "red"))

    def _mcp_info(self) -> None:
        if self.mcp is None:
            self._log(("未配置 MCP。在 config.yaml 的 mcp 段添加（如 burp），重启后生效。", "yellow"))
            return
        self._log(("MCP 服务器：", "bold"))
        self._log((self.mcp.summary(), "dim"))
        names = sorted(self.mcp.tool_names())
        if names:
            self._log((f"可用 MCP 工具（{len(names)}）：", "bold"))
            for n in names:
                self._log((f"  {n}", "dim"))

    def _help(self) -> None:
        self._log((
            "\n".join([
                "命令：",
                "  /open [url] [token]   连接并登录 GZCTF",
                "  /games                列出比赛",
                "  /game <id>            选择比赛",
                "  /challenges           列出当前比赛题目",
                "  /challenge <id>       载入题目（下载附件 / 启动容器）",
                "  /start  /close        启动 / 销毁容器题实例",
                "  /solve                让 Agent 开始解题",
                "  /models [序号]        列出可用模型 / 按序号切换",
                "  /model [名字]         查看或切换模型",
                "  /mcp                 查看 MCP 服务器与工具",
                "  /llm                 查看 LLM 后端/凭证状态",
                "  /new                 新建会话",
                "  /sessions            列出会话",
                "  /resume <序号|id>    恢复会话",
                "  /title <名字>        重命名当前会话",
                "  /undo  /redo         撤销 / 恢复上一条",
                "  /submit <flag>        提交 flag",
                "  /writeup              生成 WriteUp 草稿",
                "  /clear  /quit         清空对话 / 退出",
                "",
                "快捷键：Ctrl+V 粘贴  Ctrl+X Leader(n/l/m/c/u/r/h)  PgUp/PgDn 翻页  Esc 终止  Ctrl+W WriteUp  Ctrl+O 思考  Ctrl+L 清屏  Ctrl+Q 退出",
            ]),
            "dim",
        ))

    # ---------- 剪贴板 ----------
    def action_paste(self) -> None:
        os.makedirs(CACHE + "/paste", exist_ok=True)
        img = grab_image(CACHE + "/paste")
        if img:
            self.attachments.append(img)
            self._refresh_attach()
            self._log(("[图片] 已粘贴：", "dim"), (os.path.basename(img), "dim"))
            return
        files = grab_files()
        if files:
            self._add_files(files)
            return
        text = grab_text()
        if text:
            self.query_one("#prompt", Input).insert_text_at_cursor(text)
            self._log(("已粘贴文本到输入框。", "dim"))
        else:
            self._log(("剪贴板里没有可识别的内容。", "dim"))

    def _add_files(self, paths: list[str]) -> None:
        wd = self.workdir or self.cfg.scratch
        os.makedirs(wd, exist_ok=True)
        added = []
        for p in paths:
            if is_image(p):
                self.attachments.append(p)
                continue
            if is_video(p):
                frames = extract_frames(p, CACHE + "/frames")
                self.attachments.extend(frames)
                self._log(("[视频] 已抽帧：", "dim"), (f"{len(frames)} 帧", "dim"))
                continue
            try:
                dest = os.path.join(wd, os.path.basename(p))
                shutil.copy2(p, dest)
                added.append(os.path.basename(p))
            except Exception as e:  # noqa: BLE001
                self._log(("复制失败：", "red"), (str(e), "red"))
        if added:
            self._log(("[文件] 已加入工作目录：", "dim"), (", ".join(added), "dim"))
        self._refresh_attach()

    # ---------- 动作 ----------
    def action_writeup(self) -> None:
        self.run_worker(self._writeup())

    def action_toggle_thinking(self) -> None:
        blocks = list(self.query("Collapsible.thinking"))
        if not blocks:
            self._log(("当前没有思考过程可展开。", "dim"))
            return
        # 只要有任意一个展开着 → 全部收起；否则全部展开
        target = all(not b.collapsed for b in blocks)
        for b in blocks:
            b.collapsed = target

    def action_clear_log(self) -> None:
        self.query_one("#log", VerticalScroll).remove_children()

    # ---------- 网络动作 ----------
    async def _open(self, args: list[str]) -> None:
        url = args[0] if args else self.cfg.gzctf.url
        token = args[1] if len(args) > 1 else self.cfg.gzctf.token
        if not url:
            self._log(("用法：/open <url> [token]", "yellow"))
            return
        self.client = GZCTFClient(url, api_token=token or None)
        try:
            await asyncio.to_thread(self.client.fetch_config)
            if not token and self.cfg.gzctf.user and self.cfg.gzctf.password:
                await asyncio.to_thread(
                    self.client.login, self.cfg.gzctf.user, self.cfg.gzctf.password,
                    self.cfg.encrypt_password, self.cfg.rsa_padding,
                )
        except GZCTFError as e:
            self._log(("连接/登录失败：", "red"), (str(e), "red"))
            return
        self.container = ContainerManager(self.client)
        mode = "API Token" if token else ("账号密码" if self.cfg.gzctf.user else "未认证(公开接口)")
        self._log(("已连接 ", "green"), (url, "bold"), (f"  [{mode}]", "dim"))

    async def _models(self, args: list[str]) -> None:
        from .llm_backend import list_models

        if args and args[0].isdigit() and self.model_list:
            idx = int(args[0])
            if 0 <= idx < len(self.model_list):
                self._set_model(self.model_list[idx])
            else:
                self._log(("序号越界。", "red"))
            return
        try:
            models = await asyncio.to_thread(list_models, self.cfg, self.session_id)
        except Exception as e:  # noqa: BLE001
            self._log(("获取模型列表失败：", "red"), (str(e), "red"))
            return
        self.model_list = models
        self._log((f"可用模型（{len(models)}）：", "bold"))
        for i, m in enumerate(models):
            mark = "  ← 当前" if m == self.cfg.llm.model else ""
            self._log((f"  [{i}] ", "cyan"), (m + mark, ""))
        self._log(("用 /models <序号> 或 /model <名字> 切换。", "dim"))

    def _set_model(self, name: str) -> None:
        self.cfg.llm.model = name
        if self.session.backend is not None:
            self.session.backend.model = name
        self._log(("模型已切换：", "bold green"), (name, ""))

    async def _games(self) -> None:
        if not self.client:
            self._log(("请先 /open", "yellow")); return
        data = await asyncio.to_thread(self.client.games)
        for g in data.get("data", []):
            self._log((f"  [{g.get('id')}] ", "cyan"), (f"{g.get('title')}  {g.get('status','')}", ""))

    async def _game(self, args: list[str]) -> None:
        if not self.client or not args:
            self._log(("用法：/game <id>", "yellow")); return
        self.gid = int(args[0])
        d = await asyncio.to_thread(self.client.game_details, self.gid)
        self.challenges = [Challenge.from_json(c) for c in d.get("challenges", [])]
        self._log((f"比赛 {self.gid}：{len(self.challenges)} 道题", "bold"))

    def _print_challenges(self) -> None:
        if not self.challenges:
            self._log(("先用 /game <id> 选比赛。", "yellow")); return
        for c in self.challenges:
            self._log((f"  [{c.id}] ", "cyan"), (f"[{c.category}] {c.title} ({c.score}分)", ""))

    async def _challenge(self, args: list[str]) -> None:
        if not self.client or self.gid is None or not args:
            self._log(("用法：/challenge <id>（需先 /game）", "yellow")); return
        cid = int(args[0])
        self.challenge = next((c for c in self.challenges if c.id == cid), Challenge(cid, f"challenge-{cid}"))
        try:
            self.detail = await asyncio.to_thread(self.client.challenge_detail, self.gid, cid)
        except GZCTFError as e:
            self._log(("拉取题目失败：", "red"), (str(e), "red")); return

        self.workdir = os.path.join(
            self.cfg.workroot, _safe(self.challenge.category), f"{cid}-{_safe(self.challenge.title)}")
        os.makedirs(self.workdir, exist_ok=True)
        files = await asyncio.to_thread(self._download_attachments, self.detail, self.workdir)
        self.runner = ToolRunner(self.workdir, self.cfg.bash_timeout)
        self.session = AgentSession(self.cfg, self.runner, session_id=self.session_id)
        self.session.mcp = self.mcp

        ctx = self.detail.get("context") or {}
        entry = ctx.get("instanceEntry")
        if not files and not entry and self.container:
            info = await asyncio.to_thread(self.container.ensure, self.gid, cid, self.detail)
            entry = info.get("entry")
            if entry:
                self._log(("容器已启动：", "green"), (entry, "bold"))
            elif info.get("error"):
                self._log(("启动容器失败：", "dim"), (info["error"], "dim"))

        self._log(("已载入题目 ", "bold"), (f"[{self.challenge.category}] {self.challenge.title}", "bold"))
        self._log(("工作目录：", "dim"), (self.workdir, "dim"))
        if files:
            self._log(("附件：", "dim"), (", ".join(files), "dim"))
        if entry:
            self._log(("实例入口：", "bold yellow"), (entry, "bold yellow"))

        self.session.add_user_text(self._context_prompt(files, entry))
        self._log(("题目已加入上下文，输入 /solve 或直接提问。", "dim"))

    def _context_prompt(self, files: list[str], entry: str | None) -> str:
        ch = self.challenge
        lines = [
            f"当前题目：{ch.title}",
            f"类别：{ch.category}",
            "",
            (self.detail.get("description") or "(无描述)"),
        ]
        if self.detail.get("hints"):
            lines += ["", "提示：", *[f"- {h}" for h in self.detail["hints"]]]
        if entry:
            lines += ["", f"实例入口：{entry}"]
        if files:
            lines += ["", "附件（已在工作目录）：", *[f"- {f}" for f in files]]
        return "\n".join(lines)

    async def _start_container(self) -> None:
        if not (self.client and self.gid and self.challenge and self.container):
            self._log(("请先 /challenge 载入题目。", "yellow")); return
        info = await asyncio.to_thread(self.container.ensure, self.gid, self.challenge.id, self.detail)
        self._log(("容器：", "green"), (str(info.get("entry") or info.get("error")), "bold"))

    async def _close_container(self) -> None:
        if not (self.container and self.gid and self.challenge):
            self._log(("无容器。", "yellow")); return
        await asyncio.to_thread(self.container.destroy, self.gid, self.challenge.id)
        self._log(("容器已销毁。", "dim"))

    def _download_attachments(self, detail: dict, workdir: str) -> list[str]:
        out = []
        for url in self.client.list_local_files(detail):
            fname = _safe(os.path.basename(url.split("?")[0])) or "attachment.bin"
            try:
                self.client.download(url, os.path.join(workdir, fname))
                out.append(fname)
            except Exception as e:  # noqa: BLE001
                self._log(("附件下载失败：", "red"), (str(e), "red"))
        return out

    def _on_confirm(self, confirmed: bool) -> None:
        if not confirmed:
            self._log(("已忽略候选 flag。", "dim"))
            return
        flag = self.session.pending_flag
        if flag:
            self.run_worker(self._do_submit(flag))

    async def _do_submit(self, flag: str) -> None:
        if not (self.client and self.gid and self.challenge):
            self._log(("未载入题目，无法提交。", "yellow")); return
        try:
            sid = await asyncio.to_thread(
                self.client.submit, self.gid, self.challenge.id, flag,
                self.cfg.encrypt_password, self.cfg.rsa_padding,
            )
            st = await asyncio.to_thread(self.client.wait_status, self.gid, self.challenge.id, sid)
            color = "green" if st == "Accepted" else "red"
            self._log(("提交结果：", "bold"), (st, f"bold {color}"))
            if st == "Accepted":
                self._log(("通过！可用 /writeup 生成 WriteUp。", "bold green"))
        except GZCTFError as e:
            self._log(("提交失败：", "red"), (str(e), "red"))

    async def _writeup(self) -> None:
        if not self.challenge:
            self._log(("请先载入题目。", "yellow")); return
        meta = {
            "title": self.challenge.title,
            "category": self.challenge.category,
            "cid": self.challenge.id,
            "source": self.cfg.gzctf.url,
            "description": self.detail.get("description", ""),
        }
        flag = self.session.pending_flag or "(未记录)"
        self._log(("正在生成 WriteUp…", "dim"))
        content = await asyncio.to_thread(writeup_mod.generate, self.cfg, meta, self.session.transcript, flag)
        path = writeup_mod.save(self.workdir or self.cfg.scratch, content)
        self._log(("WriteUp 已保存：", "bold green"), (path, "green"))


def run(cfg_path: str = "config.yaml") -> None:
    # 找不到指定配置时，回退到本包所在项目的 config.yaml，避免静默使用默认值
    if not cfg_path or not os.path.exists(cfg_path):
        fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
        cfg_path = fallback if os.path.exists(fallback) else None
    cfg = load_config(cfg_path)
    # 有些终端/上一个程序会残留 Kitty 键盘协议，导致按键变成 CSI-u 乱码；启动时清掉
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\x1b[=0u")
            sys.stdout.flush()
    except Exception:
        pass
    CTFApp(cfg).run()


if __name__ == "__main__":
    run()
