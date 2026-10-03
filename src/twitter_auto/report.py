from __future__ import annotations

from datetime import datetime

from .models import CuratedIdea


def render_markdown(ideas: list[CuratedIdea], sort: str, scanned_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# AI x Crypto Reddit Curation",
        "",
        f"- Generated at: {now}",
        f"- Reddit sort: `{sort}`",
        f"- Posts scanned: {scanned_count}",
        f"- Ideas selected: {len(ideas)}",
        "",
    ]

    if not ideas:
        lines.extend(
            [
                "No strong ideas matched the current filters.",
                "",
                "Try lowering `--min-score`, increasing `--limit`, or using `--sort rising`.",
            ]
        )
        return "\n".join(lines)

    for index, idea in enumerate(ideas, start=1):
        post = idea.post
        lines.extend(
            [
                f"## {index}. {post.title}",
                "",
                f"- Source: {post.subreddit}",
                f"- Score: {idea.score}",
                f"- Reddit: {post.source_url}",
                f"- Engagement: {post.score} upvotes / {post.comments} comments",
                f"- Angle: {idea.angle}",
                f"- Why selected: {'; '.join(idea.reasons)}",
                "",
                "### Short X Draft",
                "",
                idea.short_post,
                "",
                "### Thread Outline",
                "",
            ]
        )
        for item in idea.thread_outline:
            lines.append(f"- {item}")
        lines.extend(["", "### Interaction Question", "", idea.question, ""])

    return "\n".join(lines)
