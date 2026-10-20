# QEMU 靶机（boot2root，slirp 用户态网络下如何扫描/攻击）

> 工具：`scripts/qemu_target.py`（动态 hostfwd + 并发探测 + nmap 服务识别）
> 已装：nmap、gobuster、dirsearch、nikto、hydra、wpscan、smbclient、linpeas、pspy

## 关键认知：slirp 下 nmap/dirsearch **直接扫不到 guest**
QEMU 用户态网络（`-netdev user`）是 QEMU 进程内的 NAT：guest 是 `10.0.2.15`，但**宿主机没有到它的路由**。
所以 `nmap 10.0.2.15`、`dirsearch -u http://10.0.2.15` 都打不到。
**必须**把 guest 端口 `hostfwd` 到宿主 `127.0.0.1:<端口>` 再扫。

## 启动（务必加 `-device e1000` + monitor socket）
```bash
qemu-system-x86_64 -enable-kvm -cpu host -m 2048 -smp 2 \
  -drive file=spindle.qcow2,if=virtio,format=qcow2 \
  -netdev user,id=n0,net=10.0.2.0/24,hostfwd=tcp:127.0.0.1:20022-:22 \
  -device e1000,netdev=n0 -display none \
  -monitor unix:mon.sock,server,nowait -daemonize -pidfile qemu.pid
```

## 扫描（用 qemu_target.py）
```bash
python3 ~/CTF/agent/scripts/qemu_target.py --monitor mon.sock scan --low 1-1024
python3 ~/CTF/agent/scripts/qemu_target.py --monitor mon.sock scan --ports 3000,3306,5000,8080,8443,9000
```
- 结果里 `宿主端口 -> guest 端口 服务`，例如 `40022 -> guest 22 OpenSSH 10.5`。
- 工具会自动分批（**slirp 的 hostfwd 上限约 100 条**，一次映射太多会失败）、过滤假开放、识别服务。

## 手动转发 + 直接跑 nmap / dirsearch
```bash
python3 ~/CTF/agent/scripts/qemu_target.py --monitor mon.sock fwd 80     # guest:80 -> 127.0.0.1:40080
nmap -sV -p 40080 127.0.0.1
dirsearch -u http://127.0.0.1:40080 -e php,html,txt -w ~/CTF/字典/seclists/common.txt
gobuster dir -u http://127.0.0.1:40080 -w ~/CTF/字典/seclists/common.txt -x php,html,txt
python3 ~/CTF/agent/scripts/qemu_target.py --monitor mon.sock unfwd 40080
ssh -p 20022 <user>@127.0.0.1          # 已知凭据时
```

## 两个坑
1. **假开放**：slirp 的 hostfwd 会先 accept 再连 guest，未真正开放的端口也显示 `tcpwrapped`。
   判据：连上后**立刻 EOF（无数据）= 关闭**；有 banner 或保持连接 = 开放。`qemu_target.py` 已按此过滤。
2. **hostfwd 上限 ~100 条**：不能一次性映射 1..65535；本工具按批（默认 64）处理。

## 替代方案（需 sudo，一次性）
想要让 nmap/dirsearch **直接扫 guest**，改用 tap/bridge（宿主加个网桥 + dnsmasq 给 guest 发 DHCP），
guest 和宿主同网段后就能直连。配置较重，SLIRP + hostfwd 通常够用。
