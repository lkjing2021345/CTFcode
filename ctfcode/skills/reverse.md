# Reverse 逆向

> 已装：`ghidra`(含 headless)、`radare2`、`ida`(idalib, 见 `ida` skill)、`gdb`+`pwndbg`、`jadx`、`apktool`、`pypy3`、python
> 全部可**命令行/无 GUI**执行。

## 静态侦察
```bash
file crackme
strings -n 6 crackme | grep -iE "flag|wrong|correct|success|key"
od -A x -t x1z crackme | head -30
```

## IDA（首选，见 `ida` skill）
```bash
python3 ~/CTF/agent/scripts/ida_headless.py ./crackme --funcs
python3 ~/CTF/agent/scripts/ida_headless.py ./crackme --decompile main
```

## radare2（非交互，适合 Agent）
```bash
r2 -A -q -c "afl" ./crackme                 # 列函数
r2 -A -q -c "pdf @ main" ./crackme          # 反汇编 main
r2 -A -q -c "axt @ sym.check" ./crackme     # 谁调用了 check
r2 -A -q -c "iz" ./crackme                  # 字符串
r2 -A -q -c "s main; pd 40" ./crackme       # 从 main 反汇编 40 条
```

## Ghidra headless（无 GUI，批处理）
```bash
/opt/ghidra/support/analyzeHeadless /tmp/ghproj myproj \
  -import ./crackme -postScript /path/to/DumpFuncs.py -deleteProject
```
（`analyzeHeadless` 需要 postScript 才能打印结果；简单读代码优先用 `ida` skill 或 r2。）

## gdb + pwndbg（批处理）
```bash
gdb -q -batch -ex "b main" -ex "run" -ex "ni 12" -ex "info registers" ./crackme
gdb -q -batch -ex "b *main" -ex "run" -ex "x/s \$rdi" ./crackme
```

## Android APK
```bash
jadx -d out app.apk                 # 命令行反编译 Java
grep -rin "flag\|http\|password" out/ | head
apktool d app.apk -o apkout         # 资源 + smali
apktool b apkout -o repack.apk      # 重打包
```

## Python 打包程序
```bash
strings -n 6 app.exe | grep -i pyinstaller     # 先确认是不是 PyInstaller
```
Python 3.14 的 `pyinstxtractor/uncompyle6` 用不了；用 `pycdc`（自行编译）或换 Python 3.8~3.11 环境解包反编译。

## 思路
静态读不懂就用 gdb 动态跟；重点看比较分支（strcmp）、常量、被混淆字符串。
