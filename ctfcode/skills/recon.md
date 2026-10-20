# Recon 侦察 / 枚举（Web & 服务）

> 已装：`nmap gobuster nikto hydra masscan wpscan smbclient`
> `dirsearch` 在 venv：`~/CTF/agent/venv/bin/dirsearch`（或先 `source venv/bin/activate`）
> 仍缺：`ffuf whatweb`（AUR 构建失败）→ 目录爆破直接用 **gobuster** 代替 ffuf。
> 字典：`~/CTF/字典/seclists/common.txt`、`raft-medium-directories.txt`
> ⚠️ 只对**授权目标**（CTF 靶机 / 自己的机器）使用。

## 端口 / 服务（nmap）
```bash
nmap -sV -sC -p- -T4 target                 # 全端口 + 服务识别 + 默认脚本
nmap -p- --min-rate 2000 -T4 target         # 快速全端口
nmap -sU --top-ports 50 target              # UDP 常见端口
nmap -p 80,443 --script http-title,http-headers target
nmap --script vuln -p 80 target             # 基础漏洞脚本
```

## Web 目录 / 参数枚举
```bash
gobuster dir -u http://target/ -w /usr/share/seclists/Discovery/Web-Content/common.txt -x php,txt,html
dirsearch -u http://target/ -e php,html,txt,js
ffuf -u http://target/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt
ffuf -u http://target/?p=FUZZ -w params.txt      # 参数爆破
```

## 指纹 / 漏洞扫描
```bash
whatweb -a 3 http://target/
nikto -h http://target/
wpscan --url http://target/ --enumerate u,vp   # 仅 WordPress
```

## SMB / 服务
```bash
smbclient -L //target -N
smbclient //target/share -N
# enum4linux 若装了：enum4linux -a target
```

## 口令爆破（授权范围内）
```bash
hydra -l admin -P /usr/share/wordlists/rockyou.txt ssh://target
hydra -L users.txt -P pass.txt http-post-form "/login:user=^USER^&pass=^PASS^:F=invalid"
```

## 常用字典位置
```bash
~/CTF/字典/seclists/common.txt
~/CTF/字典/seclists/raft-medium-directories.txt
/usr/share/john/password.lst
```
