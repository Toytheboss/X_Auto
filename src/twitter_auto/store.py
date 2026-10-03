from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import CuratedIdea


STATUSES = {
    "new",
    "drafted",
    "pending_approval",
    "approved",
    "published",
    "rejected",
}


class ContentStore:
    def __init__(self, path: Path | str = "data/twitter_auto.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL UNIQUE,
                    subreddit TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_score INTEGER NOT NULL,
                    source_comments INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    curation_score REAL NOT NULL,
                    reasons_json TEXT NOT NULL,
                    angle TEXT NOT NULL,
                    short_post TEXT NOT NULL,
                    thread_outline_json TEXT NOT NULL,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    published_tweet_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    idea_id INTEGER,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_ideas(self, ideas: list[CuratedIdea]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        now = self.now()
        with self.connect() as connection:
            for idea in ideas:
                post = idea.post
                existing = connection.execute(
                    "SELECT id, status FROM ideas WHERE source_url = ?",
                    (post.source_url,),
                ).fetchone()
                if existing:
                    if existing["status"] in {"published", "rejected", "approved", "pending_approval"}:
                        continue
                    connection.execute(
                        """
                        UPDATE ideas
                        SET curation_score = ?,
                            reasons_json = ?,
                            angle = ?,
                            short_post = ?,
                            thread_outline_json = ?,
                            question = ?,
                            status = 'drafted',
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            idea.score,
                            json.dumps(idea.reasons, ensure_ascii=False),
                            idea.angle,
                            idea.short_post,
                            json.dumps(idea.thread_outline, ensure_ascii=False),
                            idea.question,
                            now,
                            existing["id"],
                        ),
                    )
                    updated += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO ideas (
                        source_url,
                        subreddit,
                        title,
                        source_score,
                        source_comments,
                        author,
                        curation_score,
                        reasons_json,
                        angle,
                        short_post,
                        thread_outline_json,
                        question,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'drafted', ?, ?)
                    """,
                    (
                        post.source_url,
                        post.subreddit,
                        post.title,
                        post.score,
                        post.comments,
                        post.author,
                        idea.score,
                        json.dumps(idea.reasons, ensure_ascii=False),
                        idea.angle,
                        idea.short_post,
                        json.dumps(idea.thread_outline, ensure_ascii=False),
                        idea.question,
                        now,
                        now,
                    ),
                )
                inserted += 1
        return inserted, updated

    def list_ideas(self, status: str | None = None, limit: int = 10) -> list[sqlite3.Row]:
        query = "SELECT * FROM ideas"
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY curation_score DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            return list(connection.execute(query, params).fetchall())

    def get_idea(self, idea_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()

    def update_status(self, idea_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unsupported status: {status}")
        with self.connect() as connection:
            connection.execute(
                "UPDATE ideas SET status = ?, updated_at = ? WHERE id = ?",
                (status, self.now(), idea_id),
            )

    def update_short_post(
        self,
        idea_id: int,
        short_post: str,
        status: str = "pending_approval",
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unsupported status: {status}")
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ideas
                SET short_post = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (short_post, status, self.now(), idea_id),
            )

    def set_telegram_message(self, idea_id: int, message_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ideas
                SET telegram_message_id = ?, status = 'pending_approval', updated_at = ?
                WHERE id = ?
                """,
                (message_id, self.now(), idea_id),
            )

    def mark_published(self, idea_id: int, tweet_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ideas
                SET status = 'published', published_tweet_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (tweet_id, self.now(), idea_id),
            )

    def log_api_call(
        self,
        service: str,
        endpoint: str,
        purpose: str,
        idea_id: int | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO api_calls (service, endpoint, purpose, idea_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (service, endpoint, purpose, idea_id, self.now()),
            )

    def count_api_calls_today(self, service: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM api_calls
                WHERE service = ? AND substr(created_at, 1, 10) = ?
                """,
                (service, today),
            ).fetchone()
        return int(row["count"] if row else 0)

    def recent_api_calls(self, service: str, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT *
                    FROM api_calls
                    WHERE service = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (service, limit),
                ).fetchall()
            )
