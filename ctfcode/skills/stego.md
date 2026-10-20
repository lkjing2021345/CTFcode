# Stego 隐写

> 已装：`exiftool zsteg stegsnow sox qsstv zbarimg ffmpeg`
> **StegSolve 是 GUI 工具、本机未装**，Agent 请用 `zsteg` + Pillow/sox 脚本替代。

## 图片（按顺序做）
```bash
exiftool flag.jpg                       # 1. 元数据里可能直接有 flag/密码
zsteg -a flag.png                       # 2. 自动跑所有 LSB 通道/位平面
strings -n 6 flag.png | grep -i flag    # 3. 明文
```
Pillow 像素/位平面脚本（用 python 工具）：
```python
from PIL import Image
im = Image.open("flag.png").convert("RGB")
print("size", im.size, "px(0,0)", im.getpixel((0, 0)))
for b in range(8):                       # 导出 8 个位平面，肉眼/脚本找隐藏图
    Image.eval(im, lambda v, b=b: 255 if (v >> b) & 1 else 0).save(f"bit{b}.png")
```

## 文本空白隐写
```bash
stegsnow -C secret.txt
stegsnow -C -p "password" secret.txt
```

## 音频（全命令行，无需 GUI）
```bash
sox in.wav spec.png spectrogram             # 生成频谱图 ← 看隐藏文字/摩斯
ffmpeg -y -i in.wav -lavfi showspectrumpic=s=1280x720 spec2.png
sox in.wav rev.wav reverse                  # 倒放
sox in.wav fast.wav speed 2                 # 变速
```
SSTV：本机 `qsstv` 是 **GUI**，Agent 无法无 GUI 解码，需人工打开 qsstv。

## 二维码 / 条形码
```bash
zbarimg qr.png
```

## StegSolve（仅人工）
GUI Java 工具，AUR 源码已失效。人工需要时到 wechall 帖子自取；Agent 用 `zsteg`+Pillow 替代。
