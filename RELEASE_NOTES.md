# CTFcode v0.1.0

首个可用版本：一个能在终端里调用本地 CTF 工具、连接 GZCTF 并自动解题的助手。

## 亮点

- **终端界面**：流式思考、可折叠的工具调用、`Esc` 终止、运行中输入排队。
- **会话**：自动持久化、启动恢复、方向键选择、搜索、导出 Markdown。
- **多后端**：OpenCode Go、任意 OpenAI 兼容端点、自定义提供商（opencode 风格配置）。
- **MCP**：可接入 Burp Suite、IDA 等外部工具。
- **剪贴板**：粘贴图片/文件/文本，视频自动抽帧。
- **GZCTF**：登录、拉题、附件、容器题、提交与结果查询。

## 安装

```bash
git clone https://github.com/lkjing2021345/CTFcode
cd CTFcode
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
./bin/ctfcode
```

## 验证

```bash
./venv/bin/python tests/smoke.py   # 23 项，无网络依赖
```

详见 README 与 CHANGELOG。
