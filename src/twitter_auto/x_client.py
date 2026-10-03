from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import quote

import requests


class XClient:
    endpoint = "https://api.twitter.com/2/tweets"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        access_token: str | None = None,
        access_token_secret: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("X_API_KEY")
        self.api_secret = api_secret or os.getenv("X_API_SECRET")
        self.access_token = access_token or os.getenv("X_ACCESS_TOKEN")
        self.access_token_secret = access_token_secret or os.getenv("X_ACCESS_TOKEN_SECRET")
        self.max_post_chars = int(os.getenv("X_MAX_POST_CHARS", "800"))

    @property
    def configured(self) -> bool:
        return bool(
            self.api_key
            and self.api_secret
            and self.access_token
            and self.access_token_secret
        )

    @staticmethod
    def _quote(value: str) -> str:
        return quote(value, safe="")

    def _authorization_header(self, method: str, url: str) -> str:
        if not self.configured:
            raise RuntimeError("X API credentials are not configured.")

        oauth_params = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }
        signature_base = "&".join(
            [
                method.upper(),
                self._quote(url),
                self._quote(
                    "&".join(
                        f"{self._quote(key)}={self._quote(value)}"
                        for key, value in sorted(oauth_params.items())
                    )
                ),
            ]
        )
        signing_key = f"{self._quote(self.api_secret)}&{self._quote(self.access_token_secret)}"
        signature = base64.b64encode(
            hmac.new(
                signing_key.encode("utf-8"),
                signature_base.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        oauth_params["oauth_signature"] = signature
        header_params = ", ".join(
            f'{self._quote(key)}="{self._quote(value)}"'
            for key, value in sorted(oauth_params.items())
        )
        return f"OAuth {header_params}"

    def post_tweet(self, text: str) -> str:
        if len(text) > self.max_post_chars:
            raise ValueError(f"Tweet text is longer than {self.max_post_chars} characters.")

        response = requests.post(
            self.endpoint,
            data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": self._authorization_header("POST", self.endpoint),
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"X API post failed: {response.status_code} {response.text}")
        payload = response.json()
        tweet_id = payload.get("data", {}).get("id")
        if not tweet_id:
            raise RuntimeError(f"X API did not return a tweet id: {payload}")
        return str(tweet_id)
