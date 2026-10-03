from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .models import RedditPost


AI_TERMS = {
    "ai",
    "agent",
    "agents",
    "llm",
    "model",
    "openai",
    "claude",
    "chatgpt",
    "automation",
    "local",
}

CRYPTO_TERMS = {
    "crypto",
    "wallet",
    "token",
    "defi",
    "ethereum",
    "solana",
    "bitcoin",
    "on-chain",
    "airdrop",
    "dao",
    "zk",
    "depin",
}

POLICY_TERMS = {
    "regulation",
    "regulator",
    "policy",
    "sec",
    "cftc",
    "stablecoin",
    "election",
    "politics",
    "government",
    "congress",
    "senate",
    "law",
    "bill",
    "sanctions",
    "cbdc",
    "china",
    "chips",
    "chip",
    "deepfake",
}

DISCUSSION_TERMS = {
    "why",
    "how",
    "what",
    "analysis",
    "guide",
    "warning",
    "risk",
    "scam",
    "rug",
    "launch",
    "built",
    "released",
}


def normalize_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()))


def contains_blocked_term(post: RedditPost, blocked_terms: list[str]) -> bool:
    text = post.text_for_analysis.lower()
    return any(term.lower() in text for term in blocked_terms)


def score_post(post: RedditPost, keywords: list[str]) -> tuple[float, list[str]]:
    text = post.text_for_analysis.lower()
    words = normalize_words(text)
    reasons: list[str] = []

    keyword_hits = [keyword for keyword in keywords if keyword.lower() in text]
    ai_hits = sorted(AI_TERMS & words)
    crypto_hits = sorted(CRYPTO_TERMS & words)
    policy_hits = sorted(POLICY_TERMS & words)
    discussion_hits = sorted(DISCUSSION_TERMS & words)

    score = 0.0

    if keyword_hits:
        score += min(len(keyword_hits), 5) * 1.4
        reasons.append(f"命中关键词：{', '.join(keyword_hits[:5])}")

    if ai_hits and crypto_hits:
        score += 4.0
        reasons.append("同时包含 AI 和 Crypto 信号")
    elif ai_hits or crypto_hits:
        score += 1.5
        reasons.append("包含垂直领域信号")

    if policy_hits and (ai_hits or crypto_hits):
        score += 3.0
        reasons.append("包含政策/监管/政治交叉议题")
    elif policy_hits:
        score += 1.2
        reasons.append("包含政策/监管/政治议题")

    if discussion_hits:
        score += min(len(discussion_hits), 3) * 0.9
        reasons.append("适合展开观点或风险分析")

    if post.comments >= 20:
        score += min(math.log10(post.comments + 1) * 2, 4)
        reasons.append(f"评论活跃：{post.comments} 条")

    if post.score >= 50:
        score += min(math.log10(post.score + 1) * 1.5, 3)
        reasons.append(f"社区认可：{post.score} 分")

    hours_old = max(
        (datetime.now(timezone.utc) - post.created_at).total_seconds() / 3600,
        0.1,
    )
    if hours_old <= 24:
        score += 1.2
        reasons.append("24 小时内的新内容")

    if len(post.title) > 130:
        score -= 0.8
    if post.comments == 0 and post.score < 5:
        score -= 1.5

    return round(score, 2), reasons


def rank_posts(
    posts: list[RedditPost],
    keywords: list[str],
    blocked_terms: list[str],
    min_score: float,
) -> list[tuple[RedditPost, float, list[str]]]:
    ranked: list[tuple[RedditPost, float, list[str]]] = []
    seen: set[str] = set()

    for post in posts:
        dedupe_key = post.permalink or post.title.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        if contains_blocked_term(post, blocked_terms):
            continue

        score, reasons = score_post(post, keywords)
        if score >= min_score:
            ranked.append((post, score, reasons))

    return sorted(ranked, key=lambda item: item[1], reverse=True)
