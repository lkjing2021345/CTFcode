#!/usr/bin/env bash
# 启动 IDA MCP（idalib headless）服务器，供 ctfcode 的 MCP 客户端连接。
# 用法: ida_mcp_serve.sh <binary> [port]
#   binary : 要分析的二进制
#   port   : 默认 8745（要和 config.yaml 里 mcp.ida.url 的端口一致）
set -euo pipefail

BIN="${1:?用法: ida_mcp_serve.sh <binary> [port]}"
PORT="${2:-8745}"
export IDADIR="${IDADIR:-$HOME/ida}"
export PYTHONPATH="$IDADIR/idalib/python${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -e "$BIN" ]; then
  echo "[error] 找不到文件: $BIN" >&2
  exit 1
fi

echo "[*] IDA MCP 正在启动: http://127.0.0.1:$PORT/sse"
echo "[*] 对应 config.yaml: mcp.ida.url = \"http://127.0.0.1:$PORT/sse\""
echo "[*] 然后启动 ctfcode，用 /mcp 查看工具（应先启动本服务）"
exec uvx --from ida-pro-mcp --with 'mcp<2' idalib-mcp --host 127.0.0.1 --port "$PORT" "$BIN"
