# Pwn

> 已装：`checksec ROPgadget ropper patchelf gdb+pwndbg nasm gcc nc socat` + python `pwn`

## 第一步：查保护
```bash
checksec --file=./pwn
```
NX（栈可执行否）、PIE（地址随机）、Canary（栈检测）、RELRO（GOT 保护）。

## pwntools 模板（用 python 工具 / 存成 exp.py 跑）
```python
from pwn import *
context.log_level = 'info'
context.arch = 'amd64'

elf = ELF('./pwn')
libc = ELF('./libc.so.6', checksec=False)

p = process('./pwn')          # 本地
# p = remote('host', 1337)    # 远程

p.recvuntil(b'> ')
p.sendline(b'A' * 100)
p.send(b'payload')
p.interactive()
```
常用：`elf.sym['win']`、`elf.got['puts']`、`elf.plt['puts']`、`libc.sym['system']`、`next(elf.search(b'/bin/sh'))`。

## 找 gadget / 改 ELF
```bash
ROPgadget --binary ./pwn | grep "pop rdi"
ropper --file ./pwn --search "pop rdi"
patchelf --set-interpreter ./ld-2.31.so --set-rpath . ./pwn
patchelf --replace-needed libc.so.6 ./libc-2.31.so ./pwn
```

## gdb + pwndbg（批处理）
```bash
gdb -q -batch -ex "b *main+100" -ex "run" -ex "heap" -ex "bins" ./pwn
```

## 汇编/编译测试程序
```bash
nasm -f elf64 sc.asm -o sc.o && ld sc.o -o sc
gcc -fno-stack-protector -z execstack -no-pie -o vuln vuln.c
```

## 常见题型
1. **ret2text**：溢出返回地址 → 跳现成 backdoor
2. **ret2libc**：泄露 libc 基址 → `system("/bin/sh")`
3. **格式化字符串**：`%p` 泄地址，`%n` 写内存
4. **堆**：UAF / double free / tcache poisoning
