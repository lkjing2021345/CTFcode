"""命令行入口：识别 GZCTF 网址 -> 认证 -> 选题 -> 下载附件 -> Agent 解题 -> 确认后提交。"""
from __future__ import annotations

import argparse
import os
import sys

from .config import load_config
from .gzctf import GZCTFClient, GZCTFError
from .llm_backend import is_ready as llm_ready
from .solver import solve
from .tools import ToolRunner


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:60]


def _download_attachments(client: GZCTFClient, detail: dict, workdir: str) -> list[str]:
    files: list[str] = []
    for att in detail.get("attachments") or []:
        url = att.get("url")
        if not url:
            continue
        fname = _safe(os.path.basename(url.split("?")[0])) or "attachment.bin"
        dest = os.path.join(workdir, fname)
        try:
            client.download(url, dest)
            files.append(fname)
            print(f"    ↓ 已下载附件 {fname}")
        except Exception as e:  # noqa: BLE001
            print(f"    ! 附件下载失败 {url}: {e}")
    return files


def _pick(items: list, prompt: str) -> list:
    for i, it in enumerate(items):
        print(f"  [{i}] {it}")
    raw = input(f"{prompt}（如 0,2,3 或 a=全部）: ").strip()
    if raw.lower() == "a":
        return items
    idxs = [int(x) for x in raw.replace(" ", "").split(",") if x != ""]
    return [items[i] for i in idxs]


def main() -> None:
    ap = argparse.ArgumentParser(description="GZCTF 自动解题 Agent（半自动）")
    ap.add_argument("--url", required=True, help="GZCTF 站点，例如 https://ctf.example.com")
    ap.add_argument("-g", "--game", type=int, help="比赛 ID")
    ap.add_argument("-c", "--challenge", type=int, help="只做某道题")
    ap.add_argument("--all", action="store_true", help="做该比赛全部题目")
    ap.add_argument("--user", help="登录用户名")
    ap.add_argument("--password", help="登录密码")
    ap.add_argument("--token", help="API Token（优先于账号密码）")
    ap.add_argument("--config", default="config.yaml", help="配置文件路径")
    ap.add_argument("--workroot", default=os.path.expanduser("~/CTF/WriteUp"), help="WriteUp 根目录")
    ap.add_argument("--yes", action="store_true", help="跳过人工确认，直接提交（谨慎）")
    args = ap.parse_args()

    cfg = load_config(args.config if os.path.exists(args.config) or args.config != "config.yaml" else None)
    if not llm_ready(cfg):
        print("! 请先在 config.yaml 配置 llm.api_key（或设置 llm.backend: opencode-go 复用 OpenCode 登录）")
        sys.exit(1)

    # 1. 识别站点
    if not GZCTFClient.looks_like_gzctf(args.url):
        print(f"! {args.url} 看起来不是 GZCTF 实例（/api/config 特征不匹配），仍可继续尝试。")
    client = GZCTFClient(args.url, api_token=args.token)

    # 2. 认证
    if not args.token:
        client.fetch_config()
        if not args.user or not args.password:
            args.user = args.user or input("用户名: ").strip()
            args.password = args.password or input("密码: ").strip()
        try:
            client.login(args.user, args.password,
                         encrypt=cfg.encrypt_password, padding=cfg.rsa_padding)
            print(f"[+] 登录成功：{args.user}")
        except GZCTFError as e:
            print(f"! 登录失败：{e}")
            print("  提示：若服务器开了 EncryptApiData，请把 config.yaml 的 encrypt_password 设为 true；"
                  "或改用 --token（在平台「个人设置 → API Token」生成）。")
            sys.exit(1)
    else:
        client.fetch_config()
        print("[+] 使用 API Token 认证")
    print(f"    site_config.apiPublicKey = {'有' if client.public_key else '无'}")

    # 3. 选比赛
    gid = args.game
    if gid is None:
        games = client.games().get("data", [])
        if not games:
            print("! 没有可见的比赛")
            sys.exit(1)
        chosen = _pick([f"{g['id']}  {g.get('title')}" for g in games], "选择比赛")
        gid = int(chosen[0].split()[0])
    print(f"[*] 比赛 ID = {gid}")

    # 4. 选题
    challenges = client.challenges(gid)
    if not challenges:
        print("! 该比赛没有可做的题目（可能未参赛/未开始）")
        sys.exit(1)
    if args.challenge:
        todo = [c for c in challenges if c.id == args.challenge]
    elif args.all:
        todo = challenges
    else:
        label_to_ch = {f"{c.id}  [{c.category}] {c.title} ({c.score}分)": c for c in challenges}
        chosen = _pick(list(label_to_ch.keys()), "选择题目")
        todo = [label_to_ch[c] for c in chosen]

    # 5. 逐题解题
    results = {}
    for ch in todo:
        print(f"\n===== [{ch.category}] {ch.title} (id={ch.id}) =====")
        workdir = os.path.join(args.workroot, _safe(ch.category), f"{ch.id}-{_safe(ch.title)}")
        os.makedirs(workdir, exist_ok=True)
        print(f"    工作目录：{workdir}")
        detail = client.challenge_detail(gid, ch.id)
        files = _download_attachments(client, detail, workdir)

        runner = ToolRunner(workdir, bash_timeout=cfg.bash_timeout)
        try:
            candidate = solve(cfg, runner, ch, detail, files)
        except Exception as e:  # noqa: BLE001
            print(f"    ! 解题过程出错：{e}")
            candidate = None

        if not candidate:
            print("    × 未得到候选 flag，跳过提交")
            results[ch.id] = "no-flag"
            continue

        # 6. 半自动确认 + 提交
        ans = "y"
        if not args.yes:
            ans = input(f"    发现候选 flag: {candidate}\n    确认提交? [y/N] ").strip().lower()
        if ans != "y":
            print("    已跳过提交")
            results[ch.id] = "skipped"
            continue
        try:
            sid = client.submit(gid, ch.id, candidate,
                                encrypt=cfg.encrypt_password, padding=cfg.rsa_padding)
            st = client.wait_status(gid, ch.id, sid)
            print(f"    提交结果：{st} (submission={sid})")
            results[ch.id] = st
        except GZCTFError as e:
            print(f"    ! 提交失败：{e}")
            results[ch.id] = "submit-error"

    # 7. 汇总
    print("\n===== 汇总 =====")
    for ch in todo:
        print(f"  [{ch.category}] {ch.title}: {results.get(ch.id, '未处理')}")


if __name__ == "__main__":
    main()
