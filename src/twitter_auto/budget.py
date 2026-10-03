from __future__ import annotations

import os

from .store import ContentStore


class BudgetExceededError(RuntimeError):
    pass


class XBudget:
    def __init__(self, store: ContentStore, daily_limit: int | None = None) -> None:
        self.store = store
        self.daily_limit = daily_limit if daily_limit is not None else self._daily_limit_from_env()

    @staticmethod
    def _daily_limit_from_env() -> int:
        value = os.getenv("X_DAILY_CALL_LIMIT", "10")
        try:
            return max(int(value), 0)
        except ValueError:
            return 10

    def used_today(self) -> int:
        return self.store.count_api_calls_today("x")

    def remaining_today(self) -> int:
        return max(self.daily_limit - self.used_today(), 0)

    def ensure_available(self) -> None:
        if self.used_today() >= self.daily_limit:
            raise BudgetExceededError(
                f"X daily call limit reached: {self.used_today()}/{self.daily_limit}"
            )

    def record_publish(self, idea_id: int | None) -> None:
        self.store.log_api_call(
            service="x",
            endpoint="POST /2/tweets",
            purpose="publish approved tweet",
            idea_id=idea_id,
        )
