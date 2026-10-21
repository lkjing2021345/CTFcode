# CTFcode — 终端 CTF 助手

给它一个 GZCTF 网址，它会：**识别站点 → 登录 → 拉题目 → 下载附件 → 起容器靶机 → 用 LLM 调用本地 CTF 工具解题 → 候选 flag 人工确认后提交 → 自动生成 WriteUp 草稿**。

提供两种界面（同一个程序）：
- **TUI**：终端交互风格的交互式终端界面（默认）。
- **CLI**：命令行模式，传入参数即执行、打印结果后退出（非交互，可脚本化）。

> ⚠️ 用途：自建/校赛/练习平台的自动化与学习。正式赛事常禁止自动提交，可能被判作弊。默认交 flag 前必须人工确认。

## 目录结构

```
agent/
├── main.py                 # 入口（默认开 TUI；带 --url 走 CLI）
├── bin/ctfcode             # 仓库内启动器
├── config.example.yaml
├── requirements.txt
├── pyproject.toml
├── tests/smoke.py          # 冒烟测试
├── scripts/                # ida_headless.py / ida_mcp_serve.sh / qemu_target.py
├── .w1mer/                 # 任务与文档归档
└── ctfcode/
    ├── tui.py              # 终端界面（会话 / Leader / 导出）
    ├── cli.py              # 命令行模式
    ├── solver.py           # CLI 解题循环
    ├── llm.py              # 多模态会话（流式 + 工具调用）
    ├── llm_backend.py      # LLM 后端解析（OpenAI 兼容 / OpenCode Go）
    ├── mcp_client.py       # MCP 客户端（sse / http / stdio）
    ├── sessions.py         # 会话持久化
    ├── tools.py            # 工具（bash/python/read/write/skill/submit_flag）
    ├── skills.py           # 技能注册
    ├── skills/             # 各方向工具手册（*.md）
    ├── clipboard.py        # 剪贴板：文本/图片/文件 + 视频抽帧
    ├── gzctf.py            # GZCTF 平台 API 客户端（含容器接口）
    ├── container.py        # 容器题实例管理
    ├── writeup.py          # WriteUp 草稿生成
    └── config.py           # 配置
```

## 安装

```bash
cd ~/CTF/agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 填 LLM key，可选填 GZCTF 站点
```

启动方式（任选）：

```bash
./bin/ctfcode                 # 仓库内启动器（自动用 venv）
python main.py                # 直接跑
pip install -e . && ctfcode   # 安装后从任意目录启动
```

## 配置 `config.yaml`

### 方式一（推荐）：直连 OpenCode Go

复用你本机 OpenCode 的登录，**无需单独申请 key**。程序会调用 `opencode auth export` 动态取凭证，并自动补上 `x-opencode-session` / `x-opencode-org-id` / `User-Agent` 等必要请求头。

```yaml
llm:
  backend: "opencode-go"          # 也可 "opencode"
  model: "deepseek-v4.1-flash"    # 见下方可选模型
```

可用模型（部分）：`deepseek-v4.1-flash`、`glm-5.3-flash`、`kimi-k2.7-code`、`qwen3.8-flash`、`minimax-m3`、`longcat-2.5-preview-free`（免费）、`beam-free`（免费）等。
看图/视频帧需要**多模态模型**。

前提：本机已 `opencode auth login`（你现在就是登录状态，可直接用）。

### 方式二：普通 OpenAI 兼容端点

```yaml
llm:
  backend: ""                                  # 留空
  base_url: "https://api.deepseek.com/v1"
  api_key: "sk-你的key"
  model: "deepseek-chat"
  headers: {}                                  # 自定义请求头（可选）
```

### 方式三：自定义提供商（opencode.jsonc 兼容）

把提供商写进 `providers.jsonc`（格式与 opencode 的 `providers` 段一致）；不写则自动读取 `~/.config/opencode/opencode.jsonc`：

```jsonc
{
  "providers": {
    "qwen": {
      "name": "Qwen",
      "settings": { "baseURL": "http://127.0.0.1:8080/v1" },
      "models": {
        "qwen38": {
          "name": "Qwen3.8-27B",
          "body": { "enable_thinking": true },
          "variants": [
            { "id": "think", "body": { "enable_thinking": true } },
            { "id": "nothink", "body": { "enable_thinking": false } }
          ]
        }
      }
    }
  }
}
```

```yaml
llm:
  provider: "qwen"     # 填了 provider 就优先走它（此时 backend 留空）
  model: "qwen38"
  variant: "nothink"   # 可选
providers_file: ""     # 留空：./providers.jsonc → ~/.config/opencode/opencode.jsonc
```

- TUI 里 `/models` 会列出自定义提供商的全部模型（含 `#think` / `#nothink` 变体），`/model provider/model#variant` 切换。
- `body` 会作为 `extra_body` 透传给服务端（例如 `enable_thinking`）。
- 模型名以服务端 `/v1/models` 为准。
- `providers.jsonc` 已被 `.gitignore` 排除（可能含内网地址）。

### 其余配置

```yaml
gzctf:                      # TUI 里 /open 可直接用
  url: "https://ctf.example.com"
  token: ""                 # 推荐：平台「个人设置 → API Token」
  user: ""
  password: ""

encrypt_password: false     # 服务器开了 EncryptApiData 才 true
rsa_padding: "oaep"         # oaep 或 pkcs1
max_steps: 30
bash_timeout: 60
workroot: "~/CTF/WriteUp"
```

> 注意：OpenCode Go 按订阅额度计费，外部客户端调用会产生你账户的用量。


---

## 一、TUI 前端（默认）

```bash
./venv/bin/python main.py
```

界面：上方对话/工具调用滚动区，下方输入框，底部快捷键栏。类终端交互体验。

### 快捷键

| 键 | 作用 |
|---|---|
| **Ctrl+V** | 粘贴：优先图片 → 文件 → 文本；**视频自动抽帧**成图片 |
| **Ctrl+X** | Leader 面板：`n` 新会话 · `l` 会话 · `p` 选会话 · `m` 模型 · `c` MCP · `u` 撤销 · `r` 恢复 · `e` 导出 · `f` 搜索 · `s` 设置 · `h` 帮助 |
| **Esc** | 终止当前思考 / 工具调用（并清空排队） |
| **PageUp / PageDown** | 对话区上翻 / 下翻 |
| Ctrl+Home / Ctrl+End | 跳到顶部 / 底部 |
| Ctrl+O | 展开 / 折叠全部「思考过程」 |
| Ctrl+W | 生成 WriteUp 草稿 |
| Ctrl+L | 清屏 |
| Ctrl+Q | 退出 |
| Enter | 发送 |

> 鼠标滚轮也能滚动；**翻看历史时新消息不会把你拽回底部**（只有本来就在底部才自动跟随）。

**思考过程折叠**：模型返回的 `reasoning_content` 会显示成默认收起的「思考过程」块，**点一下标题**即可展开/收起（不抢输入焦点）。
**流式输出**：思考与回复是**边生成边显示**的——思考块在生成时自动展开，生成完自动收起；底部状态栏持续转圈。
**中断与排队**：**Esc** 终止当前思考/工具；运行期间再发消息会**排队**（底部显示「排队 N 条」），当前回合结束后按顺序自动接着跑。
**工具调用折叠**：每次工具调用显示成一行默认收起的块，标题是命令摘要（如 `bash: ls -la`），**点开看完整输出**，界面更紧凑。
**运行指示**：Agent 思考或调用工具时，底部状态栏会有转圈提示（`⠹ 思考中…` / `执行工具 bash…`），结束后自动消失。
**图标可选**：`config.yaml` 的 `ui.icons` 支持 `plain`（▸▾›●└，通用）或 `nerd`（Nerd Font 字形，需终端为 Nerd Font）。
**兼容性**：不使用 emoji；终端字体常缺 `⏺`/`⎿` 字形 在常见字体（含 JetBrainsMono NF）里缺字形，故用等价符号代替。

### 剪贴板支持

- **文本**：Ctrl+V 直接贴入输入框。
- **图片**：截图/复制的图片 → 存为文件 → 作为图片发给多模态模型（截图里的题目直接能看）。
- **文件**：拖拽进来的文件路径（或复制的文件）→ 图片作附件；视频自动用 ffmpeg 抽帧；其它文件自动复制进工作目录。
- **视频**：抽 6 帧图片喂给模型（对应视频类 Misc 题）。

> 依赖 `xclip`（X11）已装；Wayland 会回退 `wl-paste`。

### 斜杠命令

```
/open [url] [token]   连接并登录 GZCTF（不填则用 config.yaml）
/games                列出比赛
/game <id>            选择比赛
/challenges           列出当前比赛题目
/challenge <id>       载入题目（下载附件 / 自动启动容器）
/start  /close        启动 / 销毁容器题实例
/solve                让 Agent 开始解题
/models [序号]        列出可用模型 / 按序号切换
/model [名字]         查看或切换模型
/mcp                 查看 MCP 服务器与工具
/new                 新建会话
/sessions [序号]     列出会话 / 按序号切换
/resume <序号|id>    恢复某个会话
/title <名字>        重命名当前会话
/undo  /redo         撤销 / 恢复上一条
/export [路径]       导出当前会话为 Markdown
/find <关键词>       在当前会话记录里搜索
/pick                打开会话选择器（方向键）
/settings            查看当前配置（脱敏）
/submit <flag>        提交 flag
/writeup              生成 WriteUp 草稿
/clear  /quit
```

典型流程：

```
/open
/game 1
/challenge 5      ← 自动下附件、起容器
/solve            ← Agent 自己侦察、写脚本、跑工具
                  ← 出现候选 flag 时弹窗，你确认后提交
/writeup          ← 生成草稿到 ~/CTF/WriteUp/<类别>/<题号-标题>/
```

没有载入题目时，它就是一个通用 CTF 助手——你可以直接粘贴题目图片或文本问它。

### 对话历史（持久化）

- **自动持久化**：每轮结束把会话存到 `~/.local/share/gzctf-agent/sessions/<id>.json`（含上下文消息与简要记录）。
- **重启恢复**：启动时自动恢复**最近一次**会话（`ui.resume: false` 可关）。
- **新建/切换**：`/new` 新建；`/sessions` 列表；`/resume <序号|id>` 切换；`/title <名字>` 命名。
- **撤销/恢复**：`/undo` 撤回最后一条用户消息（并把原文回填到输入框，`/redo` 可恢复）。
- 顶部标题栏显示当前会话标题与 id。

配置：

```yaml
ui:
  icons: nerd
  resume: true                 # 启动是否恢复最近会话
  sessions_dir: "~/.local/share/gzctf-agent/sessions"
```

---

## 二、容器题支持

- 载入题目时，若题目无附件且详情里没有实例入口，会**自动调用 `POST /api/game/{id}/container/{challengeId}` 启动容器**，拿到 `instanceEntry`（如 `nc 1.1.1.1 1337` / `http://...`）注入上下文。
- 模型解题时可用 `bash` 里的 `nc`/`curl` 与靶机交互。
- `/close` 销毁实例释放资源；长时占用可再次 `/start`。

---

## 三、WriteUp 自动生成

`/writeup`（或 Ctrl+W）会把本次会话的**工具调用记录 + 输出 + 得到的 flag**发给 LLM，总结成规范 Markdown，保存到：

```
~/CTF/WriteUp/<类别>/<题号-标题>/writeup.md
```

LLM 不可用时退回到模板拼装版本。

---

## 四、CTF 工具 Skills

Agent 内置一套「技能手册」，把各方向工具的用法沉淀成 md，模型需要时用 `skill` 工具按需加载（省 token、更聚焦）。当前技能：

`misc`（文件识别/编码）、`stego`（图片音频隐写）、`crypto`（RSA/编码）、`web`（sqlmap/漏扫思路）、`reverse`（Ghidra/radare2/gdb）、`pwn`（pwntools/ROPgadget）、`forensics`（磁盘/内存镜像）、`mobile`（jadx/frida）、`vmimage`（VMDK/VDI→qcow2）。

手册文件在 `ctfcode/skills/*.md`，可自行增补；按需加载由 `skill` 工具完成。

> 真正**执行**工具（binwalk / zsteg / sqlmap / pwntools…）是通过 `bash` / `python` 工具在题目工作目录里跑的——skill 负责「怎么用」，bash 负责「真的跑」。

## 五、MCP（外部工具，如 Burp Suite）

内置 MCP 客户端，可连接外部 MCP 服务器，把它们的工具并进 Agent。**支持 SSE / streamable-http / stdio**。

### 连 Burp Suite（官方 MCP 扩展）
1. 在 Burp 里装扩展：**Extensions → BApp Store → “MCP Server” → Install**（或从 GitHub 下载 jar 加载）。
2. 在 Burp 的 **MCP 标签页勾选 Enabled**（默认监听 `http://127.0.0.1:9876`）。
3. `config.yaml` 已默认配好：
   ```yaml
   mcp:
     burp:
       transport: sse
       url: "http://127.0.0.1:9876/sse"
   ```
4. 启动 `ctfcode`，底部会显示「正在连接 MCP 服务器…」；用 `/mcp` 查看已连接的服务器和工具（如 `burp__send_http_request`、`burp__get_proxy_history` 等）。
5. 之后 Agent 就能直接调用这些工具（发请求、读 Proxy 历史、开 Repeater、Collaborator…）。

### 其它 MCP（stdio 示例）
```yaml
mcp:
  demo:
    transport: stdio
    command: python3
    args: ["/path/to/server.py"]
```

> 连接失败不会崩溃，只会在 `/mcp` 里显示 `[失败] 原因`。启动前确保对应服务（如 Burp）已在运行。

### 连 IDA Pro（mrexodia/ida-pro-mcp，支持 IDA 8.3+）
> 官方 Hex-Rays `ida-mcp` 要求 **IDA ≥ 9.4**；你是 9.1，请用 mrexodia 版（已实测可用，47 个工具：反编译/反汇编/交叉引用/改名/类型…）。

1. 先为**要分析的二进制**起 IDA MCP 服务（一个二进制一个服务）：
   ```bash
   ~/CTF/agent/scripts/ida_mcp_serve.sh /path/to/binary 8745
   ```
   它会在 `http://127.0.0.1:8745/sse` 提供 MCP。
2. 在 `config.yaml` 里启用（默认已注释，取消注释即可）：
   ```yaml
   mcp:
     ida:
       transport: sse
       url: "http://127.0.0.1:8745/sse"
   ```
3. 启动 `ctfcode` → `/mcp` 应看到 `[OK] ida: 47 个工具`。

> 只想**静态自动分析**、不想起服务的话，直接用 `ida` skill 的 `scripts/ida_headless.py`（打开任意二进制、无需 MCP），更省事。

## 六、命令行模式（CLI）

CLI 就是**非交互**的那条路：给它参数就跑，打印结果后退出。它和 TUI 是同一个程序，
带 `--url` 就会自动走 CLI；`--cli` 只是显式声明一下（两者等价）：

```bash
# 显式 CLI
ctfcode --cli --url https://ctf.example.com --user 你的用户名

# 直接带 --url 也会走 CLI（不用写 --cli）
ctfcode --url https://ctf.example.com -g 1 -c 5

# 做整个比赛（逐题半自动确认）
ctfcode --url https://ctf.example.com -g 1 --all --token <TOKEN>
```

---

## 常见流程示例

**解一道 GZCTF 题**
```bash
ctfcode
/open                      # 用 config.yaml 里的站点/凭证
/game 1
/challenges
/challenge 5               # 下载附件 / 起容器
/solve                     # 流式解题；候选 flag 弹窗按 Y 确认
/writeup                   # 生成草稿到 ~/CTF/WriteUp/...
```

**临时查一个附件（不连平台）**
```bash
ctfcode
Ctrl+V                     # 粘贴题目截图/文本
直接提问，例如：分析这个流量包，找出 flag
```

**用 MCP（以 Burp 为例）**
```bash
# Burp 顶部 MCP 标签启用后
/mcp                       # 确认 [OK] burp: N 个工具
让 Agent 调用 burp__get_proxy_http_history 查看历史
```

**QEMU 靶机**
```bash
python3 scripts/qemu_target.py --monitor mon.sock scan --low 1-1024
python3 scripts/qemu_target.py --monitor mon.sock fwd 80
nmap -sV -p 40080 127.0.0.1
```

**会话管理**
```bash
Ctrl+X l   或  /pick       # 方向键选会话（可输入过滤）
/find flag                 # 当前会话内搜索
/export                    # 导出 Markdown
```

## 测试

```bash
./venv/bin/python tests/smoke.py   # 无需网络/LLM，覆盖配置、工具、会话、界面挂载与快捷键
```

## 认证的两个坑

1. **RSA 加密**：部分实例开启 `EncryptApiData`，登录密码和 flag 要先用 `/api/config` 的公钥加密。设 `encrypt_password: true`，`rsa_padding` 选 `oaep`/`pkcs1`。
2. **频率限制**：交 flag 有 rate limit（429），放慢速度。

## 现实成功率

| 方向 | 预期 | 备注 |
|---|---|---|
| Misc 编码/隐写 | 🟢 高 | 强项，配合粘贴题目图片 |
| Crypto 基础 | 🟢 中高 | RSA 小攻击、编码 |
| Reverse 简单 | 🟡 中 | 依赖模型读伪代码 |
| Web 基础 | 🟡 中 | 简单注入可自动 |
| Pwn | 🔴 低 | 通常需人工 |

## 后续可扩展

- [ ] 流式输出（打字机效果）
- [ ] 多模态模型自动降级（无图模型时把图片转文字占位）
- [ ] 沙箱隔离（bubblewrap），工具白名单
- [ ] 多题并发
