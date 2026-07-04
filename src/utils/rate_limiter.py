from __future__ import annotations

from collections.abc import Callable

from tenacity import Retrying, retry, stop_after_attempt, wait_exponential
from tenacity.wait import wait_base


def with_exponential_backoff[T](func: Callable[[], T]) -> T:
    @retry(wait=wait_exponential(multiplier=1, min=1, max=30), stop=stop_after_attempt(5))
    def wrapped() -> T:
        return func()

    return wrapped()


def retry_provider_call[T](
    func: Callable[[], T],
    *,
    attempts: int = 5,
    wait_strategy: wait_base | None = None,
) -> T:
    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_strategy or wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    return retryer(func)
