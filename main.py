#!/usr/bin/env python3
"""入口。

- 直接运行 / --tui   -> 打开 TUI（交互式界面）
- --cli ...          -> 命令行模式（显式）
- 直接带 --url ...   -> 命令行模式（自动）

配置默认取本文件同目录下的 config.yaml（不受当前工作目录影响）。
"""
import os
import sys

# 某些终端对 Kitty 键盘协议支持不完整，会导致按键变成 CSI-u 乱码；必须在 import textual 之前设置
os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

TOP_HELP = """CTFcode — 终端 CTF 助手

用法:
  ctfcode                        打开终端界面（TUI）
  ctfcode --tui [--config PATH]  指定配置文件
  ctfcode --cli --url URL ...    命令行模式（批量）
  ctfcode --version              显示版本
  ctfcode --help                 显示本帮助

TUI 内输入 /help 查看全部命令与快捷键。
"""


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] in ("--version", "-V"):
        from ctfcode import __version__

        print(f"ctfcode {__version__}")
        return
    if argv and argv[0] in ("--help", "-h"):
        print(TOP_HELP)
        return

    # 显式 CLI 模式：ctfcode --cli --url ... -g 1
    if "--cli" in argv:
        argv = [a for a in argv if a != "--cli"]
        sys.argv = [sys.argv[0]] + argv
        from ctfcode.cli import main as cli_main

        cli_main()
        return

    tui = (not argv) or argv[0] in ("--tui", "-i")

    if tui:
        rest = argv[1:] if argv and argv[0] in ("--tui", "-i") else argv
        cfg = os.path.join(AGENT_DIR, "config.yaml")
        if "--config" in rest:
            cfg = rest[rest.index("--config") + 1]
        elif rest and not rest[0].startswith("-"):
            cfg = rest[0]
        from ctfcode.tui import run

        run(cfg)
    else:
        from ctfcode.cli import main as cli_main

        cli_main()


if __name__ == "__main__":
    main()
