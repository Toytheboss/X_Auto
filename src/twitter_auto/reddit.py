from __future__ import annotations

import os
from typing import Iterable

import requests

from .models import RedditPost


class RedditClient:
    def __init__(self, user_agent: str | None = None, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.user_agent = (
            user_agent
            or os.getenv("REDDIT_USER_AGENT")
            or "twitter-auto/0.1 by local-curator"
        )
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
            }
        )
        self.timeout = timeout
        self.client_id = os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.username = os.getenv("REDDIT_USERNAME")
        self.password = os.getenv("REDDIT_PASSWORD")
        self._access_token: str | None = None

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> str | None:
        if self._access_token:
            return self._access_token

        if not self.has_credentials:
            return None

        data = {"grant_type": "client_credentials"}
        if self.username and self.password:
            data = {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            }

        response = self.session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(self.client_id, self.client_secret),
            data=data,
            timeout=self.timeout,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _get_listing_payload(self, subreddit: str, sort: str, limit: int) -> dict:
        access_token = self._get_access_token()
        if access_token:
            url = f"https://oauth.reddit.com/r/{subreddit}/{sort}"
            headers = {"Authorization": f"Bearer {access_token}"}
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
            headers = {}

        response = self.session.get(
            url,
            params={"limit": limit, "raw_json": 1},
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code == 401 and access_token:
            self._access_token = None
            return self._get_listing_payload(subreddit, sort, limit)

        response.raise_for_status()
        return response.json()

    def fetch_listing(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 15,
    ) -> list[RedditPost]:
        sort = sort.lower()
        if sort not in {"hot", "new", "rising", "top"}:
            raise ValueError("sort must be one of: hot, new, rising, top")

        payload = self._get_listing_payload(subreddit, sort, limit)
        posts: list[RedditPost] = []
        for child in payload.get("data", {}).get("children", []):
            data = child.get("data", {})
            if data.get("stickied") or data.get("over_18"):
                continue

            title = str(data.get("title") or "").strip()
            if not title:
                continue

            posts.append(
                RedditPost(
                    subreddit=str(data.get("subreddit") or subreddit),
                    title=title,
                    url=str(data.get("url") or ""),
                    permalink=str(data.get("permalink") or ""),
                    author=str(data.get("author") or "unknown"),
                    score=int(data.get("score") or 0),
                    comments=int(data.get("num_comments") or 0),
                    created_utc=float(data.get("created_utc") or 0),
                    selftext=str(data.get("selftext") or "").strip(),
                )
            )

        return posts

    def fetch_many(
        self,
        subreddits: Iterable[str],
        sort: str = "hot",
        limit: int = 15,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        for subreddit in subreddits:
            try:
                posts.extend(self.fetch_listing(subreddit, sort=sort, limit=limit))
            except requests.HTTPError as error:
                print(f"Skipped r/{subreddit}: {error}")
            except requests.RequestException as error:
                print(f"Skipped r/{subreddit}: {error}")
        return posts
