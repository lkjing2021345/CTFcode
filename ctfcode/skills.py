"""CTF 工具技能手册：供 Agent 用 `skill` 工具按需查阅。

把各方向工具的用法沉淀成 md，模型需要时再加载（渐进式披露），
比一次性塞进 system prompt 更省 token、也更聚焦。
"""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(_HERE, "skills")

SKILLS: dict[str, str] = {
    "misc": "杂项:file/strings/od、嵌套 binwalk、解压 7z/unrar、编码识别(无 xxd 用 od)",
    "stego": "隐写:exiftool、zsteg、stegsnow、sox 频谱、zbarimg(StegSolve 为 GUI 用 zsteg 替代)",
    "crypto": "密码学:编码、pycryptodome、gmpy2 RSA、z3、sage、hashcat/john",
    "web": "Web:curl、sqlmap、常见漏洞、信息收集(Burp 为 GUI 用 curl)",
    "recon": "侦察/枚举:nmap 端口、gobuster/ffuf/dirsearch 目录、whatweb/nikto 指纹、hydra 爆破",
    "privesc": "提权枚举(拿 shell 后):linpeas/winpeas/pspy + SUID/sudo/cron 手工检查",
    "burp": "通过 MCP 操作 Burp(前缀 burp__):发请求/读历史/Repeater/Collaborator",
    "reverse": "逆向:file/strings、radare2 非交互、gdb 批处理、jadx/apktool、Ghidra headless",
    "ida": "IDA 无 GUI(idalib):scripts/ida_headless.py 反编译/列函数/交叉引用",
    "ida-mcp": "通过 MCP 操作 IDA(前缀 ida__):反编译/反汇编/交叉引用/读数据",
    "pwn": "Pwn:checksec、pwntools 模板、ROPgadget、patchelf、gdb+pwndbg、常见题型",
    "forensics": "取证:sleuthkit(免 root)读镜像、photorec、ewfmount、Volatility3(vol)",
    "mobile": "安卓:jadx、apktool、frida(模拟器/adb 需另装)",
    "vmimage": "虚拟机镜像:VMDK/VDI/OVA→qcow2 转换,离线用 sleuthkit 读",
    "qemu-target": "QEMU 靶机(slirp):hostfwd 转发+nmap/dirsearch 扫 guest,scripts/qemu_target.py",
}


def names() -> list[str]:
    return list(SKILLS)


def index() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in SKILLS.items())


def handle(name: str = "") -> str:
    key = (name or "").strip().lower()
    if not key or key == "list":
        return "可用技能(skill)手册:\n" + index() + "\n\n用 skill(name=\"<技能名>\") 查阅其中一份。"
    if key not in SKILLS:
        return f"未知技能 '{name}'。可用: {', '.join(SKILLS)}"
    path = os.path.join(SKILL_DIR, f"{key}.md")
    if not os.path.exists(path):
        return f"技能 '{key}' 暂无手册文件。"
    with open(path, encoding="utf-8") as f:
        return f.read()[:8000]
