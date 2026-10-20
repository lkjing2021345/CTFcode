# Burp MCP（通过 MCP 操作 Burp Suite）

> 前提：config.yaml 已配 `mcp.burp`（`http://127.0.0.1:9876`，**根路径、不加 /sse**），
> 且 Burp 顶部 **MCP 标签页已勾选 Enabled**。工具名前缀 `burp__`，用 `/mcp` 可看全部 27 个。

## 常用工具

### 发 HTTP 请求
- `burp__send_http1_request` / `burp__send_http2_request`：参数是一段**原始 HTTP 请求文本**
  （含请求行、Host、头、空行、body），返回响应。HTTP/2 别手动填 `Connection` 等受限头。

### 读数据 / 历史
- `burp__get_proxy_http_history`：Proxy HTTP 历史（可翻页）
- `burp__get_proxy_http_history_regex`：按正则过滤历史
- `burp__get_proxy_websocket_history[_regex]`：WebSocket 历史
- `burp__get_organizer_items[_regex]`：Organizer 里的条目
- `burp__get_scanner_issues`：扫描器发现的问题

### 联动工具
- `burp__create_repeater_tab[_http2]`：把请求开成 Repeater 标签
- `burp__send_to_intruder`：把请求送进 Intruder
- `burp__set_task_execution_engine_state`：暂停/恢复任务引擎
- `burp__set_proxy_intercept_state`：开/关 Proxy 拦截
- `burp__get_active_editor_contents` / `set_active_editor_contents`：读写当前编辑器内容

### 编解码 / 随机
- `burp__url_encode` / `url_decode`、`burp__base64_encode` / `base64_decode`
- `burp__generate_random_string`

### OOB / Collaborator（Pro）
- `burp__generate_collaborator_payload`：生成 Collaborator 域名
- `burp__get_collaborator_interactions`：轮询外带交互（DNS/HTTP/SMTP）

## 重要：审批
Burp MCP 默认开着 **Require approval for HTTP requests / project data access**：
- 调用 `burp__send_http1_request` 或读历史时会**弹窗要你在 Burp 里点确认**。
- 想顺畅自动化：在 **MCP 标签页 → Auto-Approved HTTP Targets** 里把目标域名加进去，
  或按需取消勾选（评估风险后）。

## 何时用 MCP、何时用 curl
- 需要**带 Burp 的会话/证书/上游代理**、或读 Proxy 历史、开 Repeater、跑 Collaborator → 用 `burp__*`。
- 单纯发个请求看回显 → `curl` 更快（见 `web` skill）。
