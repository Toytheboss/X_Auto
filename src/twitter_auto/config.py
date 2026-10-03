from __future__ import annotations

import json
from pathlib import Path


DEFAULT_CONFIG = {
    "subreddits": [
        "LocalLLaMA",
        "OpenAI",
        "CryptoCurrency",
        "ethereum",
        "solana",
        "defi",
    ],
    "keywords": [
        "ai",
        "agent",
        "wallet",
        "on-chain",
        "defi",
        "token",
        "llm",
        "automation",
    ],
    "blocked_terms": ["giveaway", "100x", "shill"],
}


def load_config(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return DEFAULT_CONFIG

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return {
        "subreddits": list(data.get("subreddits", DEFAULT_CONFIG["subreddits"])),
        "keywords": list(data.get("keywords", DEFAULT_CONFIG["keywords"])),
        "blocked_terms": list(data.get("blocked_terms", DEFAULT_CONFIG["blocked_terms"])),
    }
