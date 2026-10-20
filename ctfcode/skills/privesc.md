# PrivEsc 提权枚举（拿到初始 shell 之后）

> 脚本：`linpeas.sh` / `winPEASx64.exe`（免 sudo 安装见下）、`pspy`（AUR）
> ```bash
> mkdir -p ~/.local/bin
> curl -fsSL https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh -o ~/.local/bin/linpeas.sh && chmod +x ~/.local/bin/linpeas.sh
> ```
> ⚠️ 仅用于授权靶机。

## Linux
```bash
./linpeas.sh -a                      # 自动枚举，重点看红色/黄色
pspy64                               # 监控进程/定时任务（找可劫持的 cron）
```
手工必查：
```bash
id; uname -a; cat /etc/os-release
sudo -l                              # 可免密执行的命令
find / -perm -4000 -type f 2>/dev/null          # SUID
getcap -r / 2>/dev/null                          # capabilities
cat /etc/crontab; ls -la /etc/cron.*; crontab -l # 定时任务
find / -writable -type d 2>/dev/null | head
cat /etc/passwd | grep -v nologin
env; history
```
常见路径：SUID 滥用（GTFOBins）、sudo 通配/脚本、可写 cron、PATH 劫持、capabilities、内核漏洞。

## Windows
```bash
winPEASx64.exe quiet
```
手工必查：`whoami /priv`、`systeminfo`、服务权限、计划任务、未引用的服务路径、AlwaysInstallElevated、保存的凭据。

## 提示
- 先用 **recon** skill 拿到入口，再上本 skill 做提权枚举。
- linpeas 输出很长，优先看 `[+]` 里标红/带 “99%” 的项。
