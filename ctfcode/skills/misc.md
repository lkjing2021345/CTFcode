# Misc 杂项

> 本机已装：`file strings od hexdump binwalk 7z unrar unzip exiftool`
> 注意：**没有 `xxd`**，用 `od` / `hexdump` 代替。

## 侦察三连（拿到任何文件先做）
```bash
file mystery.bin
strings -n 6 mystery.bin | grep -iE "flag|ctf|key|pass|secret"
od -A x -t x1z mystery.bin | head -30      # 十六进制（代替 xxd）
hexdump -C mystery.bin | head -30
```

## 嵌套 / 解压
```bash
binwalk mystery.png              # 检测内嵌文件
binwalk -e mystery.png           # 提取到 _mystery.png.extracted/
7z l a.zip && 7z x a.zip         # 列/解压 zip/7z（-p 加密码）
unrar x a.rar                    # 解压 rar
unzip -o a.zip
```
文件头判断真身：`PNG` `%PDF` `PK`(zip) `Rar!` `7z` `GIF8`。**改后缀无效，看头。**

## 编码识别 + 批量试解（用 python 工具）
```python
import base64, binascii
s = b"PUT_SUSPECT_STRING_HERE"
for name, fn in [("b64", base64.b64decode), ("b32", base64.b32decode),
                 ("b16", base64.b16decode), ("hex", binascii.unhexlify)]:
    try:
        print(name, "->", fn(s))
    except Exception:
        pass
```
特征：结尾 `=` 且 64 字符集→Base64；全大写 A-Z2-7→Base32；仅 0-9a-f→Hex；`.`/`-`→摩斯。

## 没有本地 CyberChef
本机没装 CyberChef（网页版即可，但 Agent 无法联网操作页面）。用上面的 python，或 `crypto` skill 的脚本替代。
