from __future__ import annotations

import httpx
import pytest

from src.ingestion.graph_delta import (
    GraphDeltaCheckpoint,
    GraphDeltaStateExpiredError,
    run_graph_delta_sync,
)
from src.ingestion.graph_transport import GraphTransportError, HttpxGraphTransport

GRAPH_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta"


def make_transport(handler: httpx.MockTransport) -> HttpxGraphTransport:
    return HttpxGraphTransport(client=httpx.Client(transport=handler))


def test_get_json_injects_headers_and_returns_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"value": []})

    transport = make_transport(httpx.MockTransport(handler))
    payload = transport.get_json(
        GRAPH_URL,
        {"Authorization": "Bearer synthetic-token", "Prefer": "odata.maxpagesize=50"},
    )

    assert payload == {"value": []}
    assert seen[0].headers["Authorization"] == "Bearer synthetic-token"
    assert seen[0].headers["Prefer"] == "odata.maxpagesize=50"


def test_error_payload_is_returned_for_non_retryable_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={"error": {"code": "SyncStateNotFound"}})

    transport = make_transport(httpx.MockTransport(handler))
    payload = transport.get_json(GRAPH_URL, {})

    assert payload == {"error": {"code": "SyncStateNotFound"}}


def test_stale_delta_state_surfaces_through_real_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={"error": {"code": "SyncStateNotFound"}})

    transport = make_transport(httpx.MockTransport(handler))
    checkpoint = GraphDeltaCheckpoint(account_id="acct-1", delta_link=GRAPH_URL)
    bearer = "synthetic-token"

    with pytest.raises(GraphDeltaStateExpiredError):
        run_graph_delta_sync(transport, access_token=bearer, checkpoint=checkpoint)


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_retryable_statuses_raise_transport_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"code": "TooBusy"}})

    transport = make_transport(httpx.MockTransport(handler))

    with pytest.raises(GraphTransportError, match=str(status_code)):
        transport.get_json(GRAPH_URL, {})


def test_non_json_body_raises_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    transport = make_transport(httpx.MockTransport(handler))

    with pytest.raises(GraphTransportError, match="non-JSON"):
        transport.get_json(GRAPH_URL, {})


def test_non_object_json_body_raises_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    transport = make_transport(httpx.MockTransport(handler))

    with pytest.raises(GraphTransportError, match="non-object"):
        transport.get_json(GRAPH_URL, {})


def test_network_error_raises_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = make_transport(httpx.MockTransport(handler))

    with pytest.raises(GraphTransportError, match="request failed"):
        transport.get_json(GRAPH_URL, {})


def test_context_manager_closes_client() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )

    with HttpxGraphTransport(client=client) as transport:
        transport.get_json(GRAPH_URL, {})

    assert client.is_closed
