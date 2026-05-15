from __future__ import annotations

from collections.abc import Callable

from tenacity import retry, stop_after_attempt, wait_exponential


def with_exponential_backoff[T](func: Callable[[], T]) -> T:
    @retry(wait=wait_exponential(multiplier=1, min=1, max=30), stop=stop_after_attempt(5))
    def wrapped() -> T:
        return func()

    return wrapped()
