from __future__ import annotations

import json
import os
import random
import hashlib
from datetime import date
from pathlib import Path


DEFAULT_PROFILES = [
    {
        "id": "fact_brief",
        "name": "事实简报",
        "voice": "像在整理一条信息简报，语气克制，只说来源、发生了什么、涉及哪些对象。",
        "structure": "先交代事实，再补背景，最后列出仍待确认的点。",
    }
]


def load_style_profiles(path: Path = Path("config/style_profiles.json")) -> list[dict[str, str]]:
    if not path.exists():
        return DEFAULT_PROFILES
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    profiles = payload.get("profiles") or DEFAULT_PROFILES
    return list(profiles)


def choose_style_profile(profiles: list[dict[str, str]]) -> dict[str, str]:
    mode = os.getenv("STYLE_PROFILE_MODE", "daily")
    if mode == "random":
        return random.choice(profiles)

    seed = os.getenv("STYLE_PROFILE_SEED", "")
    today = date.today().isoformat()
    digest = hashlib.sha256(f"{today}:{seed}".encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(profiles)
    return profiles[index]


def render_style_prompt(profile: dict[str, str]) -> str:
    return (
        f"今日写作风格：{profile.get('name', '默认')}\n"
        f"语气：{profile.get('voice', '')}\n"
        f"结构偏好：{profile.get('structure', '')}\n"
        "注意：这是风格方向，不是固定模板。不要每条都按同一结构写。"
    )
