from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        env_path = Path(".env")
        if not env_path.exists():
            return False
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ[key.strip()] = value
        return True

from .config import load_config
from .deepseek import enhance_ideas_with_deepseek
from .drafts import curate_posts
from .feeds import FeedClient, build_feeds, load_feed_config
from .humanizer import append_source, humanize_text
from .reddit import RedditClient
from .report import render_markdown
from .sample_data import sample_posts
from .scoring import rank_posts
from .budget import BudgetExceededError, XBudget
from .store import ContentStore
from .telegram_bot import TelegramBot, read_telegram_offset
from .x_client import XClient


def add_curation_args(parser: argparse.ArgumentParser, include_output: bool = False) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/subreddits.json"),
        help="Path to subreddit and keyword config.",
    )
    parser.add_argument(
        "--feeds",
        type=Path,
        default=Path("config/feeds.json"),
        help="Path to RSS feed config.",
    )
    parser.add_argument(
        "--source",
        choices=["reddit-rss", "rss", "reddit", "both"],
        default="reddit-rss",
        help="Content source to scan. reddit-rss is the default and does not require Reddit API.",
    )
    parser.add_argument(
        "--include-reddit-rss",
        action="store_true",
        help="Include Reddit RSS feeds from config/feeds.json when using RSS source.",
    )
    parser.add_argument(
        "--sort",
        choices=["hot", "new", "rising", "top"],
        default="hot",
        help="Reddit listing to scan.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Posts to fetch per subreddit.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of curated ideas to keep.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=4.0,
        help="Minimum curation score.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use built-in sample posts instead of calling Reddit.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable DeepSeek rewriting even when DEEPSEEK_API_KEY is configured.",
    )

    if include_output:
        parser.add_argument(
            "--output",
            type=Path,
            default=Path("reports/latest.md"),
            help="Markdown report output path.",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI x Crypto Reddit-to-X automation agent."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/twitter_auto.sqlite3"),
        help="SQLite database path.",
    )
    add_curation_args(parser, include_output=True)

    subparsers = parser.add_subparsers(dest="command")

    report_parser = subparsers.add_parser("report", help="Generate a Markdown curation report.")
    add_curation_args(report_parser, include_output=True)

    collect_parser = subparsers.add_parser("collect", help="Collect ideas into the approval queue.")
    add_curation_args(collect_parser, include_output=True)

    notify_parser = subparsers.add_parser("notify", help="Send drafted ideas to Telegram for approval.")
    notify_parser.add_argument("--limit", type=int, default=5, help="Ideas to notify.")
    notify_parser.add_argument("--dry-run", action="store_true", help="Print messages instead of sending.")

    poll_parser = subparsers.add_parser("poll-telegram", help="Process Telegram approval callbacks.")
    poll_parser.add_argument("--timeout", type=int, default=5, help="Telegram long-poll timeout.")

    loop_parser = subparsers.add_parser("run-telegram-bot", help="Continuously process Telegram callbacks.")
    loop_parser.add_argument("--timeout", type=int, default=20, help="Telegram long-poll timeout.")
    loop_parser.add_argument("--interval", type=int, default=2, help="Seconds to wait between polls.")

    approve_parser = subparsers.add_parser("approve", help="Approve queued ideas locally.")
    approve_parser.add_argument("ids", nargs="*", type=int, help="Idea IDs to approve.")
    approve_parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Approve all pending_approval ideas.",
    )

    publish_parser = subparsers.add_parser("publish-approved", help="Publish approved ideas to X.")
    publish_parser.add_argument("--limit", type=int, default=3, help="Approved ideas to publish.")
    publish_parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call X API. Without this flag, marks fake dry-run tweet IDs.",
    )

    budget_parser = subparsers.add_parser("budget", help="Show X publish call budget.")
    budget_parser.add_argument("--recent", type=int, default=10, help="Recent X calls to show.")

    return parser.parse_args()


def build_ideas(args: argparse.Namespace) -> tuple[list, list]:
    config = load_config(args.config)
    if args.sample:
        posts = sample_posts()
    else:
        posts = []
        if args.source in {"rss", "reddit-rss", "both"}:
            feed_config = load_feed_config(args.feeds)
            feed_client = FeedClient()
            if args.source == "reddit-rss":
                feeds = list(feed_config.get("reddit_rss", []))
            else:
                feeds = build_feeds(feed_config, include_reddit_rss=args.include_reddit_rss)
            posts.extend(feed_client.fetch_many(feeds, limit=args.limit))

        if args.source in {"reddit", "both"}:
            client = RedditClient()
            if not client.has_credentials:
                print(
                    "No Reddit credentials found. Public Reddit JSON may return 403. "
                    "Use --source rss or fill .env for stable Reddit API access."
                )
            posts.extend(
                client.fetch_many(
                    config["subreddits"],
                    sort=args.sort,
                    limit=args.limit,
                )
            )
    ranked = rank_posts(
        posts,
        keywords=config["keywords"],
        blocked_terms=config["blocked_terms"],
        min_score=args.min_score,
    )
    ideas = curate_posts(ranked[: args.top])
    if not args.no_llm:
        ideas = enhance_ideas_with_deepseek(ideas)
    return posts, ideas


def command_report(args: argparse.Namespace) -> None:
    posts, ideas = build_ideas(args)

    markdown = render_markdown(ideas, sort=args.sort, scanned_count=len(posts))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    print(f"Scanned {len(posts)} posts, selected {len(ideas)} ideas.")
    print(f"Report written to {args.output}")


def command_collect(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    posts, ideas = build_ideas(args)
    inserted, updated = store.upsert_ideas(ideas)

    markdown = render_markdown(ideas, sort=args.sort, scanned_count=len(posts))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    print(f"Scanned {len(posts)} posts, selected {len(ideas)} ideas.")
    print(f"Queued {inserted} new ideas, updated {updated} existing drafts.")
    print(f"Report written to {args.output}")


def command_notify(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    ideas = store.list_ideas(status="drafted", limit=args.limit)
    bot = TelegramBot(store=store)

    if not ideas:
        print("No drafted ideas to notify.")
        return

    for idea in ideas:
        if args.dry_run or not bot.configured:
            print("\n--- Telegram dry-run ---")
            print(bot.build_approval_text(idea))
            store.update_status(int(idea["id"]), "pending_approval")
            continue

        message_id = bot.send_approval(idea)
        store.set_telegram_message(int(idea["id"]), message_id)
        print(f"Sent approval request for idea #{idea['id']} as Telegram message {message_id}.")


def command_poll_telegram(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    bot = TelegramBot(store=store)
    if not bot.configured:
        raise RuntimeError("Telegram bot token or chat id is not configured.")

    offset = read_telegram_offset()
    updates = bot.get_updates(offset=offset, timeout=args.timeout)
    handled = bot.handle_updates(updates)
    print(f"Processed {len(updates)} Telegram updates, handled {handled} callbacks.")


def command_run_telegram_bot(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    bot = TelegramBot(store=store)
    if not bot.configured:
        raise RuntimeError("Telegram bot token or chat id is not configured.")

    print("Telegram bot loop started. Press Ctrl+C to stop.")
    try:
        while True:
            offset = read_telegram_offset()
            updates = bot.get_updates(offset=offset, timeout=args.timeout)
            handled = bot.handle_updates(updates)
            if updates or handled:
                print(f"Processed {len(updates)} updates, handled {handled} callbacks.")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Telegram bot loop stopped.")


def command_approve(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    ids = list(args.ids)
    if args.all_pending:
        ids.extend(int(row["id"]) for row in store.list_ideas(status="pending_approval", limit=100))

    if not ids:
        print("No idea IDs provided.")
        return

    for idea_id in sorted(set(ids)):
        store.update_status(idea_id, "approved")
        print(f"Approved idea #{idea_id}.")


def command_publish_approved(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    budget = XBudget(store)
    client = XClient()
    ideas = store.list_ideas(status="approved", limit=args.limit)

    if not ideas:
        print("No approved ideas to publish.")
        return

    for idea in ideas:
        idea_id = int(idea["id"])
        text = append_source(str(idea["short_post"]).strip(), str(idea["source_url"]))
        if len(text) > client.max_post_chars:
            print(f"Skipped idea #{idea_id}: tweet is {len(text)} characters, max is {client.max_post_chars}.")
            continue

        if not args.live:
            fake_id = f"dry-run-{idea_id}"
            store.mark_published(idea_id, fake_id)
            print(f"Dry-run published idea #{idea_id} as {fake_id}.")
            continue

        if not client.configured:
            raise RuntimeError("X API credentials are not configured.")

        try:
            budget.ensure_available()
            budget.record_publish(idea_id)
            tweet_id = client.post_tweet(text)
        except BudgetExceededError as error:
            print(error)
            break

        store.mark_published(idea_id, tweet_id)
        print(f"Published idea #{idea_id} as tweet {tweet_id}.")


def command_budget(args: argparse.Namespace) -> None:
    store = ContentStore(args.db)
    budget = XBudget(store)
    print(f"X publish calls today: {budget.used_today()}/{budget.daily_limit}")
    print(f"Remaining today: {budget.remaining_today()}")
    calls = store.recent_api_calls("x", limit=args.recent)
    if not calls:
        return
    print("\nRecent X calls:")
    for call in calls:
        print(
            f"- {call['created_at']} {call['endpoint']} "
            f"idea={call['idea_id']} purpose={call['purpose']}"
        )


def main() -> None:
    load_dotenv()
    args = parse_args()
    command = args.command or "report"

    if command == "report":
        command_report(args)
    elif command == "collect":
        command_collect(args)
    elif command == "notify":
        command_notify(args)
    elif command == "poll-telegram":
        command_poll_telegram(args)
    elif command == "run-telegram-bot":
        command_run_telegram_bot(args)
    elif command == "approve":
        command_approve(args)
    elif command == "publish-approved":
        command_publish_approved(args)
    elif command == "budget":
        command_budget(args)
    else:
        raise ValueError(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
