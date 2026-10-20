# IDA Pro（无 GUI，用 idalib）

本机 IDA **Pro 9.1** 装在 `~/ida`，自带 **idalib**（无需 GUI、可用 Python 脚本驱动，含 Hex-Rays 反编译）。
**用下面的封装脚本，不要自己拼环境变量。**

## 用法

```bash
# 列出所有函数（默认动作）
python3 ~/CTF/agent/scripts/ida_headless.py <binary>

# 反编译指定函数
python3 ~/CTF/agent/scripts/ida_headless.py <binary> --decompile main
python3 ~/CTF/agent/scripts/ida_headless.py <binary> --decompile sub_1139

# 查看某地址的交叉引用
python3 ~/CTF/agent/scripts/ida_headless.py <binary> --xref 0x1234
```

## 注意
- 每次调用会**重新打开数据库**，有秒级开销；一次调用尽量多做几件事，别在循环里反复调。
- `--decompile` 需要 Hex-Rays（本机 Pro 有）；被优化的函数可能反编译失败。
- 脚本内部已设置 `IDADIR=~/ida` 和 `PYTHONPATH=~/ida/idalib/python`；如 IDA 装在别处，先 `export IDADIR=/路径`。
- 首次运行会创建配置 `~/.idapro/ida-config.json`，正常。

## 需要自己写更复杂逻辑时
```python
import os, sys
os.environ.setdefault("IDADIR", os.path.expanduser("~/ida"))
sys.path.insert(0, os.path.join(os.environ["IDADIR"], "idalib", "python"))
import idapro
idapro.open_database("/path/to/bin", run_auto_analysis=True)
import ida_funcs, ida_hexrays, idautils
# ... 你的分析 ...
idapro.close_database()
```

## 什么时候用 GUI / MCP
- 本 skill 覆盖的是**自动化静态分析**。
- 只有需要**操作你手动打开的 IDA GUI 会话**、或让**多个客户端共用**一套 IDA 工具时，才考虑 `ida-pro-mcp`（MCP 客户端 + 插件）。
- 单纯让 Agent 自动分析二进制，**idalib 这条路就够，不需要 MCP**。
