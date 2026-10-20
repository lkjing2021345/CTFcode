#!/usr/bin/env python3
"""QEMU slirp 靶机辅助工具：动态 hostfwd + 用 nmap 扫映射端口。

为什么需要它：QEMU 用户态网络(slirp)下宿主【没有到 guest 的路由】,
nmap 扫不到 guest。必须把 guest 端口 hostfwd 到宿主 loopback 再扫。
直接用「宿主端口 == guest 端口」会扫到宿主自己的服务 → 假阳性。
本工具把 guest 端口映射到【带固定偏移】的宿主端口(默认 40000+guest),
避开宿主占用端口,再用 nmap 对映射端口做服务识别。

前提：QEMU 用 `-monitor unix:mon.sock,server,nowait` 启动,netdev id 默认 n0。

用法：
  qemu_target.py info
  qemu_target.py fwd 80                 # guest:80 -> 127.0.0.1:40080
  qemu_target.py fwd 80 50080           # 指定宿主端口
  qemu_target.py unfwd 40080
  qemu_target.py scan --low 1-1024      # 分批映射 1..1024 并探测（slirp 上限约 100/批）
  qemu_target.py scan --ports 3000,3306,8080,8443

环境变量：QEMU_MONITOR 覆盖 monitor 路径(默认 ./mon.sock)，NETDEV 覆盖 id(默认 n0)。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import socket
import subprocess
import sys
import threading
import time


class Monitor:
    """连 QEMU monitor，后台线程持续读，避免回显塞满 socket 卡死。"""

    def __init__(self, path: str, netdev: str = "n0"):
        self.netdev = netdev
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.sock.settimeout(0.2)
        self._buf = b""
        self._stop = False
        self._t = threading.Thread(target=self._drain, daemon=True)
        self._t.start()
        time.sleep(0.3)

    def _drain(self) -> None:
        while not self._stop:
            try:
                d = self.sock.recv(65536)
                if not d:
                    break
                self._buf += d
            except socket.timeout:
                continue
            except OSError:
                break

    def cmd(self, line: str) -> str:
        self._buf = b""
        self.sock.sendall((line + "\n").encode())
        time.sleep(0.04)
        return self._buf.decode("utf-8", "ignore")

    def add(self, guest: int, host: int) -> bool:
        out = self.cmd(f"hostfwd_add {self.netdev} tcp:127.0.0.1:{host}-:{guest}")
        return "Could not set up host forwarding" not in out

    def remove(self, host: int) -> None:
        self.cmd(f"hostfwd_remove {self.netdev} tcp:127.0.0.1:{host}")

    def close(self) -> None:
        self._stop = True


def _parse_ports(args) -> list[int]:
    ports: list[int] = []
    if args.low:
        m = re.match(r"^(\d+)-(\d+)$", args.low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            ports += list(range(a, b + 1))
        else:
            ports.append(int(args.low))
    for p in (args.ports or "").split(","):
        p = p.strip()
        if p:
            ports.append(int(p))
    return sorted(set(ports))


def _nmap(host_ports: list[int]) -> dict[int, str]:
    """对一批宿主端口跑 nmap -sV，返回 {host_port: service}。"""
    if not host_ports:
        return {}
    spec = ",".join(str(p) for p in host_ports)
    cmd = ["nmap", "-Pn", "-sV", "--version-light", "-p", spec, "127.0.0.1"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
    except FileNotFoundError:
        print("[error] 未找到 nmap，请先安装：sudo pacman -S nmap", file=sys.stderr)
        sys.exit(1)
    res: dict[int, str] = {}
    for line in out.splitlines():
        m = re.match(r"^(\d+)/tcp\s+open\s+(\S+)(?:\s+(.*))?$", line.strip())
        if m:
            res[int(m.group(1))] = (m.group(3) or m.group(2)).strip()
    return res


def _probe(host_port: int, timeout: float = 1.5):
    """连宿主映射端口判断 guest 该端口是否真开放。
    slirp 会先 accept 再连 guest：guest 拒绝 -> 立刻 EOF(视为关闭)；
    guest 接受 -> 有 banner 或保持连接(视为开放)。返回 True/False。
    """
    try:
        s = socket.create_connection(("127.0.0.1", host_port), timeout=timeout)
    except OSError:
        return False
    try:
        s.settimeout(timeout)
        data = s.recv(256)
        return data != b""          # b"" = peer 立刻关闭 -> 关闭
    except socket.timeout:
        return True                 # 无 banner 但保持连接（如 HTTP）-> 开放
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def cmd_scan(m: Monitor, ports: list[int], offset: int, batch: int = 64) -> None:
    """分批映射（slirp hostfwd 有约 100 条上限）→ 并发探测 → 清除。"""
    total = len(ports)
    all_open: dict[int, int] = {}  # host -> guest
    for i in range(0, total, batch):
        chunk = [g for g in ports[i:i + batch] if offset + g <= 65535]
        mapping: dict[int, int] = {}
        for g in chunk:
            host = offset + g
            if m.add(g, host):
                mapping[host] = g
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch) as ex:
            for hp, ok in zip(mapping, ex.map(_probe, mapping)):
                if ok:
                    all_open[hp] = mapping[hp]
        for hp in mapping:
            m.remove(hp)
        print(f"    进度 {min(i+batch, total)}/{total}，累计开放 {len(all_open)}", end="\r")
    print(" " * 40, end="\r")
    # 重新映射已确认开放的端口，供 nmap -sV 识别服务（否则映射已被清除）
    for hp, g in all_open.items():
        m.add(g, hp)
    res = _nmap(sorted(all_open))
    for hp in all_open:
        m.remove(hp)
    print("=== 真实开放服务（宿主端口 -> guest 端口）===")
    if not all_open:
        print("  (无)")
    for hp in sorted(all_open):
        print(f"  {hp} -> guest {all_open[hp]:>5}   {res.get(hp, '?')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="QEMU slirp 靶机 hostfwd + nmap 扫描")
    ap.add_argument("--monitor", default=os.environ.get("QEMU_MONITOR", "mon.sock"))
    ap.add_argument("--netdev", default=os.environ.get("NETDEV", "n0"))
    ap.add_argument("--offset", type=int, default=40000)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info")
    p_fwd = sub.add_parser("fwd")
    p_fwd.add_argument("guest", type=int)
    p_fwd.add_argument("host", type=int, nargs="?")
    p_un = sub.add_parser("unfwd")
    p_un.add_argument("host", type=int)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--low", help="端口或区间，如 1-1024 或 22")
    p_scan.add_argument("--ports", help="逗号分隔，如 3000,3306,8080")
    p_scan.add_argument("--offset", type=int, default=None)
    p_scan.add_argument("--batch", type=int, default=64, help="每批映射数（slirp 上限约 100，默认 64）")

    args = ap.parse_args()
    if not os.path.exists(args.monitor):
        print(f"[error] 找不到 monitor socket: {args.monitor}（QEMU 用 -monitor unix:{args.monitor},server,nowait 启动）", file=sys.stderr)
        sys.exit(1)
    m = Monitor(args.monitor, args.netdev)
    try:
        if args.cmd == "info":
            print(m.cmd("info network"))
        elif args.cmd == "fwd":
            host = args.host or (args.offset + args.guest)
            ok = m.add(args.guest, host)
            print(f"{'[OK]' if ok else '[!!]'} guest {args.guest} -> 127.0.0.1:{host}")
        elif args.cmd == "unfwd":
            m.remove(args.host)
            print(f"[OK] removed 127.0.0.1:{args.host}")
        elif args.cmd == "scan":
            ports = _parse_ports(args)
            offset = args.offset if args.offset is not None else 40000
            cmd_scan(m, ports, offset, args.batch)
    finally:
        m.close()


if __name__ == "__main__":
    main()
