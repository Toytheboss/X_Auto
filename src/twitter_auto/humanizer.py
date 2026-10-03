from __future__ import annotations

import re
import os


PHRASE_REPLACEMENTS = {
    "值得注意的是": "",
    "此外，": "",
    "此外": "",
    "这不只是一个新闻点，": "",
    "更像是": "更接近",
    "早期信号": "早期苗头",
    "如果这个趋势继续发展，中文圈很可能会晚半拍才开始讨论。": "中文圈可能还没怎么聊，但我会先放进观察列表。",
    "不是单纯的热点": "不只是热点",
    "把讨论翻译成可操作判断，而不是搬运标题": "别只搬标题，关键是拆出能不能落地",
    "这个框架其实": "这个思路",
    "比大部分 agent 叙事务实": "比单纯讲 agent 概念实在一点",
    "每个环节都能出事": "这里很容易翻车",
    "离能跑还有距离": "离真的能用还远",
    "值得跟，但别急着信。": "我会先观察。",
    "值得跟，但别急着信": "我会先观察",
    "可验证的东西": "能看得见的实现",
    "核心不是": "重点不是",
    "本身就很难": "挺难",
}


def humanize_text(text: str) -> str:
    """Lightweight Chinese humanizer for short X drafts.

    This is intentionally deterministic so publishing never depends on an LLM call.
    It removes common AI-writing markers and makes the draft more direct.
    """
    output = text.strip()
    for old, new in PHRASE_REPLACEMENTS.items():
        output = output.replace(old, new)

    output = re.sub(r"我的判断：\s*", "我更关心的是：", output)
    output = re.sub(r"这不仅仅?是(.+?)，而是", r"这不是\1，重点是", output)
    output = re.sub(
        r"AI agent 现在最大的问题不是不够聪明，是没法自己花钱。?",
        "我现在更关心 AI agent 能不能安全花钱。",
        output,
    )
    output = re.sub(r"先看有没有人把(.+?)做成(.+?)。?", r"先看有没有人真把\1跑出来。", output)
    output = re.sub(r"[ \t]+", " ", output)
    output = re.sub(r"\n{3,}", "\n\n", output)
    output = output.replace("。。", "。").replace("，，", "，")

    lines = [line.strip() for line in output.splitlines()]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


def source_suffix(source_url: str) -> str:
    return f"来源：{source_url.strip()}"


def append_source(text: str, source_url: str) -> str:
    output = humanize_text(text)
    lines = [line for line in output.splitlines() if not line.strip().startswith("来源：")]
    output = "\n".join(lines).strip()
    if os.getenv("APPEND_SOURCE_TO_POST", "false").lower() not in {"1", "true", "yes"}:
        return output
    if not source_url or source_url in output:
        return output
    return f"{output}\n\n{source_suffix(source_url)}"
