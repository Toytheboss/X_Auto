from __future__ import annotations

from .humanizer import humanize_text
from .models import CuratedIdea, RedditPost


def infer_angle(post: RedditPost, reasons: list[str]) -> str:
    text = post.text_for_analysis.lower()

    if any(term in text for term in ["scam", "rug", "phishing", "risk"]):
        return "风险提醒"
    if any(term in text for term in ["agent", "wallet", "on-chain", "automation"]):
        return "AI Agent 与链上执行能力"
    if any(term in text for term in ["tokenomics", "airdrop", "launch", "token"]):
        return "项目机制与市场叙事"
    if any(term in text for term in ["local", "llm", "model", "open source"]):
        return "开源模型与加密应用结合"
    if "评论活跃" in " ".join(reasons):
        return "社区争议与真实反馈"
    return "趋势观察"


def build_short_post(post: RedditPost, angle: str) -> str:
    return humanize_text(
        f"我看到一条关于「{post.title}」的信息值得看。\n\n"
        f"我的判断：它更像是「{angle}」方向的早期信号。\n\n"
        "如果这个趋势继续发展，中文圈很可能会晚半拍才开始讨论。"
    )


def build_thread_outline(post: RedditPost, angle: str) -> list[str]:
    return [
        humanize_text(item)
        for item in [
        f"开头：这条信息很有意思：{post.title}",
        f"背景：它指向的是「{angle}」，不是单纯的热点。",
        "核心观察：英文社区关注的不是概念本身，而是实际可用性、风险和机会。",
        "中文用户价值：把讨论翻译成可操作判断，而不是搬运标题。",
        "结尾互动：你觉得这个方向是短期叙事，还是会变成真实需求？",
    ]
    ]


def build_question(angle: str) -> str:
    return humanize_text(f"你觉得「{angle}」在 AI x Crypto 里是真机会，还是又一轮叙事包装？")


def curate_post(post: RedditPost, score: float, reasons: list[str]) -> CuratedIdea:
    angle = infer_angle(post, reasons)
    return CuratedIdea(
        post=post,
        score=score,
        reasons=reasons,
        angle=angle,
        short_post=build_short_post(post, angle),
        thread_outline=build_thread_outline(post, angle),
        question=build_question(angle),
    )


def curate_posts(ranked_posts: list[tuple[RedditPost, float, list[str]]]) -> list[CuratedIdea]:
    return [curate_post(post, score, reasons) for post, score, reasons in ranked_posts]
