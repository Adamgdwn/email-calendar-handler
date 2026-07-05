from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

GRAPH_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 30.0


class GraphTransportError(RuntimeError):
    """Raised for transport-level Microsoft Graph failures; safe to retry."""


class HttpxGraphTransport:
    """Real `GraphTransport` implementation over httpx.

    Non-retryable 4xx payloads are returned rather than raised because
    `graph_delta` inspects Graph error bodies to detect stale delta state;
    429/5xx raise `GraphTransportError` so `retry_provider_call` can back off.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)

    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            msg = f"Microsoft Graph request failed: {exc!r}"
            raise GraphTransportError(msg) from exc
        if response.status_code in GRAPH_RETRYABLE_STATUS_CODES:
            msg = f"Microsoft Graph returned retryable status {response.status_code}"
            raise GraphTransportError(msg)
        try:
            payload = response.json()
        except ValueError as exc:
            msg = f"Microsoft Graph returned a non-JSON body with status {response.status_code}"
            raise GraphTransportError(msg) from exc
        if not isinstance(payload, dict):
            msg = "Microsoft Graph returned a non-object JSON body"
            raise GraphTransportError(msg)
        return payload

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpxGraphTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
