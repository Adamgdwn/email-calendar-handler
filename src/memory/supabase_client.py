"""Typed Supabase access: settings, client factory, and the narrow table gateway.

Stores depend on the `TableGateway` protocol, so tests run against in-memory
fakes and the postgrest fluent API stays contained to this module.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from supabase import Client, create_client


class SupabaseStoreError(RuntimeError):
    """Raised when Supabase returns rows the memory stores cannot use."""


class SupabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SUPABASE_", extra="ignore")

    url: AnyHttpUrl
    service_role_key: SecretStr

    @field_validator("service_role_key")
    @classmethod
    def service_role_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            msg = "service_role_key must not be blank"
            raise ValueError(msg)
        return value


class TableGateway(Protocol):
    def select_rows(
        self,
        table: str,
        columns: str,
        *,
        eq: dict[str, str],
        in_filter: tuple[str, list[str]] | None = None,
        gte: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def upsert_rows(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]: ...

    def update_rows(
        self, table: str, values: dict[str, Any], *, eq: dict[str, str]
    ) -> list[dict[str, Any]]: ...


class SupabaseTableGateway:
    """`TableGateway` implementation over the supabase-py fluent API."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def select_rows(
        self,
        table: str,
        columns: str,
        *,
        eq: dict[str, str],
        in_filter: tuple[str, list[str]] | None = None,
        gte: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        query = self._client.table(table).select(columns)
        for column, value in eq.items():
            query = query.eq(column, value)
        if in_filter is not None:
            column, values = in_filter
            query = query.in_(column, values)
        if gte is not None:
            column, bound = gte
            query = query.gte(column, bound)
        return _dict_rows(query.execute().data)

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        return _dict_rows(self._client.table(table).insert(rows).execute().data)

    def upsert_rows(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        response = self._client.table(table).upsert(rows, on_conflict=on_conflict).execute()
        return _dict_rows(response.data)

    def update_rows(
        self, table: str, values: dict[str, Any], *, eq: dict[str, str]
    ) -> list[dict[str, Any]]:
        query = self._client.table(table).update(values)
        for column, value in eq.items():
            query = query.eq(column, value)
        return _dict_rows(query.execute().data)


def build_supabase_client(settings: SupabaseSettings) -> Client:
    return create_client(
        str(settings.url).rstrip("/"),
        settings.service_role_key.get_secret_value(),
    )


def build_table_gateway(settings: SupabaseSettings) -> TableGateway:
    return SupabaseTableGateway(build_supabase_client(settings))


def _dict_rows(data: list[Any]) -> list[dict[str, Any]]:
    return [row for row in data if isinstance(row, dict)]
