# Roadmap

## v0.1.0（已完成）

- [x] 终端 TUI：流式输出、折叠、终止、排队
- [x] 会话持久化 / 恢复 / 搜索 / 选择器 / 导出
- [x] GZCTF：登录、拉题、附件、容器题
- [x] LLM：OpenCode Go / OpenAI 兼容 / 自定义提供商
- [x] MCP 客户端（SSE / HTTP / stdio）
- [x] 剪贴板图文与视频抽帧
- [x] 技能手册与 WriteUp 草稿

## v0.2（计划）

- [ ] 提供商连通性探测 `/providers`（列出 -> 模型 -> 延迟）
- [ ] 模型列表缓存，减少远端请求
- [ ] 会话选择器支持模糊搜索与预览
- [ ] Web 端只读查看会话（可选）
- [ ] Docker 镜像与 `docker compose` 一键启动
- [ ] 发布 PyPI 包，支持 `pip install ctfcode`

## 长期

- [ ] 更多平台适配（CTFd 等）
- [ ] 插件化工具与技能
- [ ] 结构化解题报告（按题目归档）
