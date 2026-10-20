"""剪贴板读取：文本、图片、文件路径；视频自动抽帧转成图片。

X11 用 xclip，Wayland 回退 wl-paste。图片以 data URL 形式喂给多模态模型。
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from urllib.parse import unquote, urlparse

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, bytes]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception:
        return 1, b""


def _xclip(*args: str) -> tuple[int, bytes]:
    return _run(["xclip", "-selection", "clipboard", *args])


def grab_image(dest_dir: str) -> str | None:
    """从剪贴板取图片存到 dest_dir，返回路径；没有图片则 None。"""
    os.makedirs(dest_dir, exist_ok=True)
    for target, ext in (("image/png", "png"), ("image/jpeg", "jpg"), ("image/webp", "webp")):
        code, data = _xclip("-t", target, "-o")
        if code == 0 and data and _looks_like_image(data):
            path = os.path.join(dest_dir, f"paste_{_ts()}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
            return path
    return None


def grab_files() -> list[str]:
    """从剪贴板取文件路径（uri-list 优先，其次把文本按行当作路径判断）。"""
    paths: list[str] = []
    code, data = _xclip("-t", "text/uri-list", "-o")
    if code == 0 and data:
        for line in data.decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if line.startswith("file://"):
                p = unquote(urlparse(line).path)
                if os.path.exists(p):
                    paths.append(p)
    if not paths:
        text = grab_text()
        if text:
            for line in text.splitlines():
                line = line.strip().strip("'\"")
                if line and os.path.exists(line):
                    paths.append(line)
    # 去重保序
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def grab_text() -> str | None:
    code, data = _xclip("-o")
    if code == 0:
        return data.decode("utf-8", "ignore")
    if shutil.which("wl-paste"):
        code, data = _run(["wl-paste", "--no-newline"])
        if code == 0:
            return data.decode("utf-8", "ignore")
    return None


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXT


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXT


def extract_frames(video: str, dest_dir: str, every_seconds: int = 2, max_frames: int = 6) -> list[str]:
    """把视频按固定间隔抽帧成 png，返回帧文件列表。"""
    if not shutil.which("ffmpeg"):
        return []
    os.makedirs(dest_dir, exist_ok=True)
    pattern = os.path.join(dest_dir, f"frame_{_ts()}_%02d.png")
    code, _ = _run([
        "ffmpeg", "-y", "-i", video,
        "-vf", f"fps=1/{every_seconds}",
        "-frames:v", str(max_frames),
        pattern,
    ], timeout=120)
    frames = sorted(
        os.path.join(dest_dir, f)
        for f in os.listdir(dest_dir)
        if f.startswith(os.path.basename(pattern).split("%")[0]) and f.endswith(".png")
    )
    return frames if code == 0 else frames


def image_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
    if ext == "jpg":
        ext = "jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/{ext};base64,{b64}"


def _looks_like_image(data: bytes) -> bool:
    sigs = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF", b"BM")
    return any(data.startswith(s) for s in sigs)


def _ts() -> str:
    import time
    return str(int(time.time() * 1000))
