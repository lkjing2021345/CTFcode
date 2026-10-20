"""把常见异常翻译成可读提示，避免界面直接抛原始堆栈信息。"""
from __future__ import annotations


def friendly(exc: BaseException) -> str:
    name = type(exc).__name__

    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return "认证失败：请检查 API key / 登录状态（可用 /llm 查看）"
        if isinstance(exc, openai.RateLimitError):
            return "触发频率限制：稍后重试或更换模型"
        if isinstance(exc, openai.APITimeoutError):
            return "请求超时：网络较慢或后端无响应"
        if isinstance(exc, openai.APIConnectionError):
            return "网络连接失败：检查网络 / 代理 / 后端地址"
    except Exception:
        pass

    try:
        from .gzctf import GZCTFError

        if isinstance(exc, GZCTFError):
            return str(exc)
    except Exception:
        pass

    if isinstance(exc, FileNotFoundError):
        return f"文件不存在：{exc.filename or ''}".rstrip("：")
    if isinstance(exc, TimeoutError):
        return "操作超时"
    if isinstance(exc, PermissionError):
        return f"权限不足：{exc.filename or ''}".rstrip("：")

    msg = str(exc).strip()
    return f"{name}: {msg}" if msg else name
