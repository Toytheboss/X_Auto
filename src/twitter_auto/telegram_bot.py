from __future__ import annotations

import json
import os
import sqlite3

import requests

from .budget import BudgetExceededError, XBudget
from .config import load_config
from .deepseek import enhance_ideas_with_deepseek
from .drafts import curate_posts
from .feeds import FeedClient, build_feeds, load_feed_config
from .humanizer import humanize_text
from .reddit import RedditClient
from .scoring import rank_posts
from .store import ContentStore
from .x_client import XClient


class TelegramBot:
    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        store: ContentStore | None = None,
    ) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.store = store

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def api_url(self, method: str) -> str:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")
        return f"https://api.telegram.org/bot{self.token}/{method}"

    @staticmethod
    def build_approval_text(idea: sqlite3.Row) -> str:
        return (
            f"待审批内容 #{idea['id']}\n\n"
            f"来源：{idea['subreddit']}\n"
            f"评分：{idea['curation_score']}\n"
            f"角度：{idea['angle']}\n"
            f"原帖：{idea['source_url']}\n\n"
            f"短推草稿：\n{idea['short_post']}\n\n"
            f"编辑：/edit {idea['id']} 新文案\n"
            f"命令批准：/approve {idea['id']}\n"
            f"命令拒绝：/reject {idea['id']}"
        )

    @staticmethod
    def approval_keyboard(idea_id: int) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"approve:{idea_id}"},
                    {"text": "Reject", "callback_data": f"reject:{idea_id}"},
                ],
                [{"text": "Edit", "callback_data": f"later:{idea_id}"}],
            ]
        }

    def send_message(self, text: str, reply_markup: dict | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Telegram bot token or chat id is not configured.")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        response = requests.post(
            self.api_url("sendMessage"),
            json=payload,
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"Telegram sendMessage failed: {response.status_code} {response.text}")
        return response.json()

    def send_approval(self, idea: sqlite3.Row) -> int:
        payload = self.send_message(
            self.build_approval_text(idea),
            reply_markup=self.approval_keyboard(int(idea["id"])),
        )
        message_id = payload["result"]["message_id"]
        return int(message_id)

    def get_updates(self, offset: int | None = None, timeout: int = 5) -> list[dict]:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(self.api_url("getUpdates"), params=params, timeout=timeout + 10)
        if not response.ok:
            raise RuntimeError(f"Telegram getUpdates failed: {response.status_code} {response.text}")
        return list(response.json().get("result", []))

    def answer_callback(self, callback_query_id: str, text: str) -> None:
        response = requests.post(
            self.api_url("answerCallbackQuery"),
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=20,
        )
        if not response.ok:
            print(f"Telegram answerCallbackQuery failed: {response.status_code} {response.text}")

    def edit_message(self, chat_id: int | str, message_id: int, text: str) -> None:
        response = requests.post(
            self.api_url("editMessageText"),
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if not response.ok:
            print(f"Telegram editMessageText failed: {response.status_code} {response.text}")

    def handle_updates(self, updates: list[dict], offset_file: str = "data/telegram_offset.json") -> int:
        if not self.store:
            raise RuntimeError("ContentStore is required to handle Telegram callbacks.")

        handled = 0
        max_update_id: int | None = None
        for update in updates:
            update_id = int(update["update_id"])
            max_update_id = update_id if max_update_id is None else max(max_update_id, update_id)
            message = update.get("message")
            if message:
                handled += self.handle_message_command(message)
                continue

            callback = update.get("callback_query")
            if not callback:
                continue

            data = str(callback.get("data") or "")
            action, _, raw_idea_id = data.partition(":")
            if action not in {"approve", "reject", "later"} or not raw_idea_id.isdigit():
                continue

            idea_id = int(raw_idea_id)
            if action == "approve":
                self.store.update_status(idea_id, "approved")
                answer = f"Approved #{idea_id}"
                self.send_message(f"已批准 #{idea_id}。")
            elif action == "reject":
                self.store.update_status(idea_id, "rejected")
                answer = f"Rejected #{idea_id}"
                self.send_message(f"已拒绝 #{idea_id}。")
            else:
                answer = f"Send /edit {idea_id} 新文案"
                self.send_message(
                    f"要编辑 #{idea_id}，直接发送：\n/edit {idea_id} 你的新文案\n\n"
                    f"改完后发送 /approve {idea_id}，或再点 Approve。"
                )

            self.answer_callback(str(callback["id"]), answer)
            handled += 1

        if max_update_id is not None:
            os.makedirs(os.path.dirname(offset_file), exist_ok=True)
            with open(offset_file, "w", encoding="utf-8") as file:
                json.dump({"offset": max_update_id + 1}, file)

        return handled

    def handle_message_command(self, message: dict) -> int:
        text = str(message.get("text") or "").strip()
        if not text.startswith("/"):
            return 0

        parts = text.split(maxsplit=2)
        command = parts[0].split("@", 1)[0].lower()

        if command == "/edit":
            if len(parts) < 3 or not parts[1].isdigit():
                self.send_message("用法：/edit 文章ID 新文案")
                return 1
            idea_id = int(parts[1])
            new_text = humanize_text(parts[2])
            self.store.update_short_post(idea_id, new_text, status="pending_approval")
            self.send_message(f"已更新 #{idea_id}。确认无误后发送 /approve {idea_id}，或点原消息的 Approve。")
            return 1

        if command in {"/approve", "/reject"}:
            if len(parts) < 2 or not parts[1].isdigit():
                self.send_message(f"用法：{command} 文章ID")
                return 1
            idea_id = int(parts[1])
            status = "approved" if command == "/approve" else "rejected"
            self.store.update_status(idea_id, status)
            self.send_message(f"已{('批准' if status == 'approved' else '拒绝')} #{idea_id}。")
            return 1

        if command == "/status":
            self.send_message(self.build_status_text())
            return 1

        if command == "/help":
            self.send_message(self.build_help_text())
            return 1

        if command == "/budget":
            self.send_message(self.build_budget_text())
            return 1

        if command == "/queue":
            status = parts[1] if len(parts) >= 2 else None
            self.send_message(self.build_queue_text(status=status))
            return 1

        if command == "/collect":
            top, source = self.parse_collect_args(parts[1:])
            self.send_message(f"开始采集，source={source}, top={top}。这可能需要几十秒。")
            self.send_message(self.collect_content(top=top, source=source))
            return 1

        if command == "/notify":
            limit = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 5
            sent = self.notify_drafts(limit=limit)
            self.send_message(f"已发送 {sent} 条待审批内容。")
            return 1

        if command == "/publish":
            limit = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 1
            self.send_message(self.publish_approved(limit=limit))
            return 1

        return 0

    @staticmethod
    def build_help_text() -> str:
        return "\n".join(
            [
                "可用命令：",
                "/help - 查看命令",
                "/status - 查看队列和 X 调用次数",
                "/budget - 查看 X 发布预算",
                "/queue - 查看队列",
                "/queue approved - 查看某个状态",
                "/collect 5 - 默认从 Reddit RSS 采集 5 条",
                "/collect 5 rss - 从非 Reddit RSS 多源采集",
                "/collect 5 reddit-rss - 从 Reddit RSS 采集",
                "/notify 5 - 发送 5 条草稿给你审批",
                "/edit 文章ID 新文案 - 编辑草稿",
                "/approve 文章ID - 批准",
                "/reject 文章ID - 拒绝",
                "/publish 1 - 发布 1 条 approved 内容到 X",
            ]
        )

    @staticmethod
    def parse_collect_args(args: list[str]) -> tuple[int, str]:
        top = 5
        source = "reddit-rss"
        allowed_sources = {"reddit-rss", "rss", "reddit", "both"}
        for arg in args:
            if arg.isdigit():
                top = int(arg)
            elif arg in allowed_sources:
                source = arg
        return top, source

    def build_status_text(self) -> str:
        lines = ["当前队列："]
        for status in ["drafted", "pending_approval", "approved", "published", "rejected"]:
            rows = self.store.list_ideas(status=status, limit=20)
            if rows:
                ids = ", ".join(f"#{row['id']}" for row in rows)
                lines.append(f"- {status}: {ids}")
        if len(lines) == 1:
            lines.append("- 空")
        budget = XBudget(self.store)
        lines.append(f"\nX 发布调用：{budget.used_today()}/{budget.daily_limit}")
        return "\n".join(lines)

    def build_budget_text(self) -> str:
        budget = XBudget(self.store)
        lines = [
            f"X 发布调用：{budget.used_today()}/{budget.daily_limit}",
            f"今日剩余：{budget.remaining_today()}",
        ]
        calls = self.store.recent_api_calls("x", limit=5)
        if calls:
            lines.append("\n最近调用：")
            lines.extend(
                f"- {call['created_at']} idea=#{call['idea_id']} {call['purpose']}"
                for call in calls
            )
        return "\n".join(lines)

    def build_queue_text(self, status: str | None = None) -> str:
        statuses = [status] if status else ["drafted", "pending_approval", "approved", "published", "rejected"]
        lines: list[str] = []
        for current_status in statuses:
            rows = self.store.list_ideas(status=current_status, limit=20)
            ids = ", ".join(f"#{row['id']}" for row in rows) if rows else "空"
            lines.append(f"{current_status}: {ids}")
        return "\n".join(lines)

    def collect_content(self, top: int = 5, source: str = "reddit-rss", limit: int = 20) -> str:
        posts = []
        feed_config = load_feed_config(None)
        if source in {"reddit-rss", "rss", "both"}:
            if source == "reddit-rss":
                feeds = list(feed_config.get("reddit_rss", []))
            else:
                feeds = build_feeds(feed_config, include_reddit_rss=(source == "both"))
            posts.extend(FeedClient().fetch_many(feeds, limit=limit))

        if source in {"reddit", "both"}:
            config = load_config(None)
            posts.extend(
                RedditClient().fetch_many(
                    config["subreddits"],
                    sort="rising",
                    limit=limit,
                )
            )

        config = load_config(None)
        ranked = rank_posts(
            posts,
            keywords=config["keywords"],
            blocked_terms=config["blocked_terms"],
            min_score=2.5,
        )
        ideas = curate_posts(ranked[:top])
        ideas = enhance_ideas_with_deepseek(ideas)
        inserted, updated = self.store.upsert_ideas(ideas)
        return f"采集完成：扫描 {len(posts)} 条，入选 {len(ideas)} 条，新增 {inserted}，更新 {updated}。"

    def notify_drafts(self, limit: int = 5) -> int:
        ideas = self.store.list_ideas(status="drafted", limit=limit)
        sent = 0
        for idea in ideas:
            message_id = self.send_approval(idea)
            self.store.set_telegram_message(int(idea["id"]), message_id)
            sent += 1
        return sent

    def publish_approved(self, limit: int = 1) -> str:
        budget = XBudget(self.store)
        client = XClient()
        if not client.configured:
            return "X API 凭证未配置，无法发布。"

        ideas = self.store.list_ideas(status="approved", limit=limit)
        if not ideas:
            return "没有 approved 内容可发布。"

        published: list[str] = []
        for idea in ideas:
            idea_id = int(idea["id"])
            text = humanize_text(str(idea["short_post"]).strip())
            if len(text) > 280:
                published.append(f"跳过 #{idea_id}：超过 280 字。")
                continue
            try:
                budget.ensure_available()
                budget.record_publish(idea_id)
                tweet_id = client.post_tweet(text)
                self.store.mark_published(idea_id, tweet_id)
                published.append(f"已发布 #{idea_id}: {tweet_id}")
            except BudgetExceededError as error:
                published.append(str(error))
                break
            except Exception as error:
                published.append(f"发布 #{idea_id} 失败：{error}")
                break

        return "\n".join(published)


def read_telegram_offset(path: str = "data/telegram_offset.json") -> int | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    offset = payload.get("offset")
    return int(offset) if offset is not None else None
