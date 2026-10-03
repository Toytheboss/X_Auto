from __future__ import annotations

from datetime import datetime, timezone

from .models import RedditPost


def sample_posts() -> list[RedditPost]:
    now = datetime.now(timezone.utc).timestamp()
    return [
        RedditPost(
            subreddit="LocalLLaMA",
            title="AI agents are useless until they can safely use wallets on-chain",
            url="https://example.com/ai-agent-wallets",
            permalink="/r/LocalLLaMA/comments/sample1/ai_agents_wallets/",
            author="sample_user",
            score=182,
            comments=67,
            created_utc=now - 3600 * 4,
            selftext=(
                "The real unlock may be agents that can read chain state, "
                "control spending limits, and execute bounded transactions."
            ),
        ),
        RedditPost(
            subreddit="defi",
            title="Warning: fake AI trading bot airdrop is draining wallets",
            url="https://example.com/fake-ai-trading-bot",
            permalink="/r/defi/comments/sample2/fake_ai_trading_bot/",
            author="sample_defi",
            score=96,
            comments=41,
            created_utc=now - 3600 * 8,
            selftext=(
                "Several users reported a phishing flow disguised as an AI "
                "trading bot beta invite."
            ),
        ),
        RedditPost(
            subreddit="ethereum",
            title="Could autonomous agents become the next DAO operators?",
            url="https://example.com/agent-dao-operators",
            permalink="/r/ethereum/comments/sample3/agent_dao_operators/",
            author="sample_eth",
            score=74,
            comments=25,
            created_utc=now - 3600 * 12,
            selftext=(
                "Discussion around AI agents voting, monitoring proposals, "
                "and triggering treasury workflows."
            ),
        ),
    ]
