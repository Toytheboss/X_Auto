from __future__ import annotations

import os
from dataclasses import replace

import requests

from .humanizer import humanize_text
from .models import CuratedIdea
from .style_profiles import choose_style_profile, load_style_profiles, render_style_prompt


STYLE_PROMPT = """你是一个中文 X/Twitter 自媒体编辑，账号定位是 AI x Crypto 事实型信息整理。

请基于输入信息，写一条中文推文。不要翻译原文，要二创。

风格要求：
- 冷静、直接、事实优先
- 不替读者下结论，不输出强个人观点
- 可以说明"目前已知""还不确定""需要观察"，但不要装作已经验证
- 不要鸡血，不要喊单，不要投资建议
- 不要使用"财富密码""百倍""起飞"等投机词
- 少用 AI 味重的表达，比如"这不仅是……更是……""值得注意的是""标志着"
- 不要写成新闻评论稿，不要每段都总结得很完整
- 少用"框架""叙事""早期信号""可验证的东西""核心不是"这类抽象词
- 多讲来源、事实、机制、风险、实际用处
- 像真人在 X 上整理信息，不像新闻稿或研究报告
- 允许短句。允许一点不确定。不要写金句式结尾

输出要求：
- 只输出推文正文
- 中文
- 300-600 字
- 不要 hashtag
- 不要 emoji
"""


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.target_chars = int(os.getenv("DEEPSEEK_TARGET_CHARS", "600"))
        self.style_profile = choose_style_profile(load_style_profiles())

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def rewrite_tweet(self, idea: CuratedIdea) -> str:
        if not self.configured:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")

        post = idea.post
        user_prompt = f"""来源：{post.subreddit}
标题：{post.title}
链接：{post.source_url}
摘要：{post.selftext[:800]}
角度：{idea.angle}
入选原因：{"；".join(idea.reasons)}
初稿：
{idea.short_post}
"""
        response = requests.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": f"{STYLE_PROMPT}\n\n{render_style_prompt(self.style_profile)}"},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            },
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"DeepSeek request failed: {response.status_code} {response.text}")
        payload = response.json()
        content = humanize_text(payload["choices"][0]["message"]["content"])
        return self.fit_tweet_length(content, limit=self.target_chars)

    def fit_tweet_length(self, text: str, limit: int = 240) -> str:
        text = humanize_text(text)
        if len(text) <= limit:
            return text

        response = requests.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是中文社交媒体编辑。把输入压缩成一条中文 X 推文，"
                            "保留事实和具体机制，删除铺垫、结论腔和个人观点。不要 hashtag，不要 emoji，"
                            "不要投资建议。少用抽象词，像真人整理信息。"
                            f"必须少于 {limit} 个中文字符。只输出正文。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0.5,
                "max_tokens": 350,
            },
            timeout=45,
        )
        if not response.ok:
            return text[:limit].rstrip()
        payload = response.json()
        shortened = humanize_text(payload["choices"][0]["message"]["content"])
        return shortened if len(shortened) <= 280 else shortened[:limit].rstrip()


def enhance_ideas_with_deepseek(ideas: list[CuratedIdea]) -> list[CuratedIdea]:
    client = DeepSeekClient()
    if not client.configured:
        return ideas

    enhanced: list[CuratedIdea] = []
    for idea in ideas:
        try:
            rewritten = client.rewrite_tweet(idea)
            enhanced.append(replace(idea, short_post=rewritten))
        except Exception as error:
            print(f"DeepSeek skipped idea '{idea.post.title}': {error}")
            enhanced.append(replace(idea, short_post=humanize_text(idea.short_post)))
    return enhanced
