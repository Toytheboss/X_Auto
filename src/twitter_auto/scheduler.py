from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from .cli import command_collect, command_notify


def run_daily_pipeline(
    db: Path = Path("data/twitter_auto.sqlite3"),
    config: Path = Path("config/subreddits.json"),
    feeds: Path = Path("config/feeds.json"),
    output: Path = Path("reports/latest.md"),
    source: str = "reddit-rss",
    sort: str = "rising",
    limit: int = 20,
    top: int = 10,
    min_score: float = 4.0,
    sample: bool = False,
    include_reddit_rss: bool = False,
    no_llm: bool = False,
    telegram_dry_run: bool = False,
) -> None:
    command_collect(
        Namespace(
            db=db,
            config=config,
            feeds=feeds,
            output=output,
            source=source,
            sort=sort,
            limit=limit,
            top=top,
            min_score=min_score,
            sample=sample,
            include_reddit_rss=include_reddit_rss,
            no_llm=no_llm,
        )
    )
    command_notify(
        Namespace(
            db=db,
            limit=top,
            dry_run=telegram_dry_run,
        )
    )
