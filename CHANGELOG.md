# Changelog

## v0.1.0 — 2026-10-21

### Features

- **终端界面**：流式思考、折叠的思考/工具调用、`Esc` 终止、运行中输入排队。
- **会话**：本地持久化、启动恢复、`/sessions`、方向键选择器、`/find` 搜索、`/export` 导出 Markdown、`/undo` `/redo`。
- **GZCTF**：站点识别、登录/Token、拉题、下载附件、容器题实例启动、提交与结果轮询。
- **LLM 后端**：OpenCode Go（复用本机登录）、任意 OpenAI 兼容端点、自定义提供商（兼容 opencode 的 `providers.jsonc`，支持模型变体与 `extra_body`）。
- **MCP**：SSE / streamable HTTP / stdio 客户端，可接入 Burp、IDA 等外部工具。
- **剪贴板**：文本、图片、文件；视频自动抽帧后交给多模态模型。
- **技能手册**：misc / stego / crypto / web / recon / privesc / reverse / ida / ida-mcp / pwn / forensics / mobile / vmimage / qemu-target / burp。
- **其他**：WriteUp 草稿生成；QEMU slirp 靶机扫描辅助脚本（`scripts/qemu_target.py`）。

### Fixes

- 中止后 `tool_calls` 历史不完整导致 API 400：新增历史自愈，并在取消时补齐 tool 回复。
- 模态框内快捷键失效、关闭后焦点不归位。
- 未找到 `config.yaml` 时静默使用默认值，现给出明确提示。
- `/models` 等待远端列表导致卡顿，改为先显示本地提供商模型。

### Docs & Infra

- 中/英文 README、CI 徽章、截图与 GIF 演示。
- GitHub Actions 运行冒烟测试；ruff 配置；Makefile。
- 冒烟测试 23 项（无网络/LLM 依赖）。
