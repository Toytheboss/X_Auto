from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class RedditPost:
    subreddit: str
    title: str
    url: str
    permalink: str
    author: str
    score: int
    comments: int
    created_utc: float
    selftext: str = ""

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.created_utc, tz=timezone.utc)

    @property
    def source_url(self) -> str:
        if self.permalink.startswith("http"):
            return self.permalink
        return f"https://www.reddit.com{self.permalink}"

    @property
    def text_for_analysis(self) -> str:
        return f"{self.title}\n{self.selftext}".strip()


@dataclass(frozen=True)
class CuratedIdea:
    post: RedditPost
    score: float
    reasons: list[str] = field(default_factory=list)
    angle: str = ""
    short_post: str = ""
    thread_outline: list[str] = field(default_factory=list)
    question: str = ""
