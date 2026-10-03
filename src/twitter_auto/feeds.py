from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests

from .models import RedditPost


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def load_feed_config(path: Path | None) -> dict:
    if path is None:
        path = Path("config/feeds.json")
    if not path.exists():
        raise FileNotFoundError(f"Feed config file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_datetime(value: str | None) -> float:
    if not value:
        return datetime.now(timezone.utc).timestamp()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return datetime.now(timezone.utc).timestamp()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def link_from_entry(element: ElementTree.Element) -> str:
    direct = child_text(element, "link")
    if direct:
        return direct
    for child in element:
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href
    return ""


class FeedClient:
    def __init__(self, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "twitter-auto/0.1 feed-curator",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            }
        )
        self.timeout = timeout

    @staticmethod
    def google_news_feeds(queries: list[str]) -> list[dict[str, str]]:
        return [
            {
                "name": f"Google News: {query}",
                "url": GOOGLE_NEWS_RSS.format(query=quote_plus(query)),
            }
            for query in queries
        ]

    def fetch_feed(self, name: str, url: str, limit: int = 10) -> list[RedditPost]:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)

        items = [element for element in root.iter() if local_name(element.tag) in {"item", "entry"}]
        posts: list[RedditPost] = []
        for item in items[:limit]:
            title = child_text(item, "title")
            if not title:
                continue
            link = link_from_entry(item) or url
            summary = (
                child_text(item, "description")
                or child_text(item, "summary")
                or child_text(item, "content")
            )
            author = child_text(item, "author") or child_text(item, "creator") or name
            published = (
                child_text(item, "pubDate")
                or child_text(item, "published")
                or child_text(item, "updated")
            )

            posts.append(
                RedditPost(
                    subreddit=name,
                    title=strip_html(title),
                    url=link,
                    permalink=link,
                    author=strip_html(author),
                    score=0,
                    comments=0,
                    created_utc=parse_datetime(published),
                    selftext=strip_html(summary),
                )
            )
        return posts

    def fetch_many(self, feeds: list[dict[str, str]], limit: int = 10) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for feed in feeds:
            name = str(feed["name"])
            url = str(feed["url"])
            try:
                posts.extend(self.fetch_feed(name=name, url=url, limit=limit))
            except (requests.RequestException, ElementTree.ParseError) as error:
                print(f"Skipped feed {name}: {error}")
        return posts


def build_feeds(config: dict, include_reddit_rss: bool = True) -> list[dict[str, str]]:
    feeds = FeedClient.google_news_feeds(list(config.get("google_news_queries", [])))
    feeds.extend(list(config.get("feeds", [])))
    if include_reddit_rss:
        feeds.extend(list(config.get("reddit_rss", [])))
    return feeds
