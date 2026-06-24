from __future__ import annotations

import pytest
from tenacity import wait_none

from src.utils.rate_limiter import retry_provider_call


def test_retry_provider_call_retries_until_success() -> None:
    attempts = 0

    def flaky_call() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("synthetic provider quota failure")
        return "ok"

    result = retry_provider_call(flaky_call, attempts=3, wait_strategy=wait_none())

    assert result == "ok"
    assert attempts == 3


def test_retry_provider_call_reraises_after_attempts() -> None:
    attempts = 0

    def failing_call() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("synthetic provider quota failure")

    with pytest.raises(RuntimeError):
        retry_provider_call(failing_call, attempts=2, wait_strategy=wait_none())

    assert attempts == 2
