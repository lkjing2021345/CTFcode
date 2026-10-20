#!/usr/bin/env python3
"""无 GUI 驱动 IDA Pro（idalib）的小工具。

用法：
    python3 scripts/ida_headless.py <binary>                 # 默认列出函数
    python3 scripts/ida_headless.py <binary> --funcs
    python3 scripts/ida_headless.py <binary> --decompile main
    python3 scripts/ida_headless.py <binary> --decompile sub_1139
    python3 scripts/ida_headless.py <binary> --xref 0x1234

依赖本机 IDA Pro 的 idalib（默认 ~/ida，可用环境变量 IDADIR 覆盖）。
"""
from __future__ import annotations

import argparse
import os
import sys

IDA_DIR = os.environ.get("IDADIR", os.path.expanduser("~/ida"))
os.environ.setdefault("IDADIR", IDA_DIR)
sys.path.insert(0, os.path.join(IDA_DIR, "idalib", "python"))


def _find_func_by_name(name: str):
    import ida_funcs

    f = ida_funcs.get_next_func(0)
    while f:
        if ida_funcs.get_func_name(f.start_ea) == name:
            return f
        f = ida_funcs.get_next_func(f.start_ea)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="headless IDA via idalib")
    ap.add_argument("binary")
    ap.add_argument("--funcs", action="store_true", help="列出所有函数")
    ap.add_argument("--decompile", metavar="NAME", help="反编译指定函数")
    ap.add_argument("--xref", metavar="EA", help="查看某地址的交叉引用")
    args = ap.parse_args()

    try:
        import idapro
    except Exception as e:  # noqa: BLE001
        print(f"[error] 无法导入 idalib，检查 IDADIR={IDA_DIR}: {e}")
        sys.exit(1)

    if not os.path.exists(args.binary):
        print(f"[error] 文件不存在: {args.binary}")
        sys.exit(1)

    rc = idapro.open_database(args.binary, run_auto_analysis=True)
    if rc != 0:
        print(f"[error] open_database 返回 {rc}")
        sys.exit(1)

    try:
        import ida_funcs

        if args.decompile:
            import ida_hexrays

            f = _find_func_by_name(args.decompile)
            if not f:
                print(f"[error] 找不到函数 {args.decompile}（先用 --funcs 看名字）")
            else:
                try:
                    print(str(ida_hexrays.decompile(f.start_ea)))
                except Exception as e:  # noqa: BLE001
                    print(f"[error] 反编译失败（可能无 Hex-Rays 或函数被优化）: {e}")
        elif args.xref:
            import idautils

            ea = int(args.xref, 0)
            for x in idautils.XrefsTo(ea):
                print(f"{hex(x.frm)}  ->  {hex(ea)}  (type={x.type})")
        else:  # 默认列函数
            f = ida_funcs.get_next_func(0)
            while f:
                print(f"{hex(f.start_ea)}  {ida_funcs.get_func_name(f.start_ea)}")
                f = ida_funcs.get_next_func(f.start_ea)
    finally:
        idapro.close_database()


if __name__ == "__main__":
    main()
