# Crypto 密码学

> 已装：python 库 `gmpy2 pycryptodome sympy z3`、`sage`、`hashcat john`
> 用 `python` 工具跑脚本时这些库都在（venv 已含）。

## 编码
见 `misc` skill 的批量试解。摩斯：
```python
morse = ".... . .-.. .-.. ---"     # 贴入题目
table = {'.-':'A','-...':'B','-.-.':'C','-..':'D','.':'E','..-.':'F','--.':'G',
         '....':'H','..':'I','.---':'J','-.-':'K','.-..':'L','--':'M','-.':'N',
         '---':'O','.--.':'P','--.-':'Q','.-.':'R','...':'S','-':'T','..-':'U',
         '...-':'V','.--':'W','-..-':'X','-.--':'Y','--..':'Z',
         '-----':'0','.----':'1','..---':'2','...--':'3','....-':'4','.....':'5',
         '-....':'6','--...':'7','---..':'8','----.':'9'}
print(''.join(table.get(c, c) for c in morse.split()))
```

## RSA（gmpy2 + pycryptodome）
```python
import gmpy2
from Crypto.Util.number import long_to_bytes, bytes_to_long, inverse

# 小公钥指数 e=3 → 直接开方
m, exact = gmpy2.iroot(c, e); print(long_to_bytes(int(m)))

# 模不互素（两个 n 有公因子）
p = gmpy2.gcd(n1, n2); q1 = n1 // p
d = pow(e, -1, (p-1)*(q1-1)); print(long_to_bytes(pow(c1, d, n1)))

# 已知 p,q
d = pow(e, -1, (p-1)*(q-1)); print(long_to_bytes(pow(c, d, n)))
```
常见攻击：小 e 开方、共模（同 n 不同 e）、模不互素、Wiener（d 很小）、已知 p/q、e 与 φ 不互素。

## 对称加密
```python
from Crypto.Cipher import AES, DES
pt = AES.new(key, AES.MODE_ECB).decrypt(ct)
```

## z3（约束/方程）
```python
from z3 import *
x = Int('x'); s = Solver(); s.add(2 * x + 1 == 11); s.check(); print(s.model())
```

## Sage（大数分解 / 离散对数 / 格）
```bash
sage -c 'print(factor(2**67-1))'
sage -c 'print(discrete_log(Mod(3,17), Mod(5,17)))'
```

## 哈希爆破（本机无 rockyou，先用自带字典）
```bash
hashcat -m 0 hash.txt /usr/share/john/password.lst       # -m 0=MD5
john --wordlist=/usr/share/john/password.lst hash.txt
john --format=raw-md5 --wordlist=/usr/share/john/password.lst hash.txt
```
需要 rockyou：放到 `~/CTF/字典/rockyou.txt` 再用，或 `sudo pacman -S wordlists`。

## 编码识别表
| 特征 | 可能是 |
|---|---|
| 结尾 `=`，64 字符集 | Base64 |
| 全大写 A-Z2-7 | Base32 |
| 仅 0-9 a-f | Hex |
| `.`/`-` 序列 | 摩斯 |
