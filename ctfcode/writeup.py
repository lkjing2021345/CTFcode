"""根据解题过程自动生成 WriteUp 草稿（Markdown）。"""
from __future__ import annotations

import os
from datetime import datetime

from openai import OpenAI

from .config import Config
from .llm_backend import resolve as resolve_backend

_TEMPLATE = """# {title}

- **方向**：{category}
- **题号**：{cid}
- **来源**：{source}
- **日期**：{date}

## 题目描述

{description}

## 解题过程

{steps}

## Flag

```
{flag}
```

## 复盘

- 关键点：{keypoint}
- 用到的工具：{tools}
"""


def _fallback(meta: dict, transcript: list[str], flag: str) -> str:
    tools = sorted({
        line.split(":", 1)[1].split("]", 1)[0].strip()
        for line in transcript
        if line.startswith("[tool:")
    })
    steps = "\n\n".join(transcript) if transcript else "（无记录）"
    return _TEMPLATE.format(
        title=meta.get("title", "题目"),
        category=meta.get("category", "Misc"),
        cid=meta.get("cid", ""),
        source=meta.get("source", ""),
        date=datetime.now().strftime("%Y-%m-%d"),
        description=meta.get("description", "（无）"),
        steps=steps,
        flag=flag or "未解出",
        keypoint="（待补充）",
        tools=", ".join(tools) or "（待补充）",
    )


def generate(cfg: Config, meta: dict, transcript: list[str], flag: str) -> str:
    """优先用 LLM 把过程总结成规范 WriteUp；失败则退回模板拼装。"""
    raw = "\n".join(transcript)[:20000]
    prompt = f"""请根据下面的解题记录，写一篇简洁规范的中文 CTF WriteUp（Markdown 格式）。

题目信息：
- 标题：{meta.get('title')}
- 方向：{meta.get('category')}
- 描述：{meta.get('description', '')[:2000]}
- 最终 Flag：{flag or '未解出'}

解题记录（含工具调用与输出）：
{raw}

要求：包含「题目描述 / 解题思路 / 关键步骤（含命令）/ 得到 Flag / 复盘」几个小节，
语言精炼，命令用代码块。直接输出 Markdown，不要额外解释。"""
    try:
        backend = resolve_backend(cfg)
        client = OpenAI(base_url=backend.base_url, api_key=backend.api_key,
                        default_headers=backend.headers)
        resp = client.chat.completions.create(
            model=backend.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            **({"extra_body": backend.extra_body} if backend.extra_body else {}),
        )
        text = resp.choices[0].message.content
        if text and text.strip():
            return text
    except Exception:
        pass
    return _fallback(meta, transcript, flag)


def save(workdir: str, content: str, name: str = "writeup.md") -> str:
    os.makedirs(workdir, exist_ok=True)
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
