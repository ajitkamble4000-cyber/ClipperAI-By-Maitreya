"""Thin Postgres helpers (psycopg 3 + pool). Service-role connection: callers enforce access."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url.get_secret_value(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def conn() -> Iterator[Connection[dict[str, Any]]]:
    with pool().connection() as c:
        yield c


@contextmanager
def transaction() -> Iterator[Connection[dict[str, Any]]]:
    with pool().connection() as c, c.transaction():
        yield c


def _adapt(params: Sequence[Any] | dict[str, Any] | None) -> Any:
    def one(v: Any) -> Any:
        return (
            Jsonb(v) if isinstance(v, dict) or (isinstance(v, list) and v and isinstance(v[0], dict)) else v
        )

    if params is None:
        return None
    if isinstance(params, dict):
        return {k: one(v) for k, v in params.items()}
    return [one(v) for v in params]


def fetch_one(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict[str, Any] | None:
    with conn() as c:
        return c.execute(sql, _adapt(params)).fetchone()


def fetch_all(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with conn() as c:
        return c.execute(sql, _adapt(params)).fetchall()


def execute(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> int:
    with conn() as c:
        return c.execute(sql, _adapt(params)).rowcount


def jsonb(value: Any) -> Jsonb:
    return Jsonb(value)


def dumps(value: Any) -> str:
    return json.dumps(value, default=str)
