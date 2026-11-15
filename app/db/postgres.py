"""PostgreSQL-backed repository (used with Supabase in production).

Each record is a JSONB document in ``documents(collection, id, data)``, which maps
one-to-one onto the Repository interface. All values are passed as bound query
parameters; field names are validated against a strict pattern, so no user input
is ever interpolated into SQL.
"""

import json
import re
import uuid
from typing import Any

from psycopg import sql
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.db.base import Filter

SCHEMA = """
create table if not exists documents (
  collection text not null,
  id         text not null,
  data       jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (collection, id)
);
create index if not exists documents_data_gin on documents using gin (data jsonb_path_ops);
alter table documents enable row level security;
"""

_FIELD_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
_OPS = {"==": "=", "!=": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


def _field(name: str) -> str:
    if not _FIELD_RE.match(name):
        raise ValueError(f"Invalid field name: {name!r}")
    return name


def _condition(field: str, op: str, value: Any) -> tuple[sql.Composable, list[Any]]:
    if op == "in":
        return sql.SQL("(data ->> %s) = any(%s)"), [field, [str(v) for v in value]]
    operator = sql.SQL(_OPS[op])  # From a fixed whitelist, never from user input.
    if isinstance(value, str):
        # Byte-wise ("C") comparison keeps ISO dates and timestamps in chronological order.
        return sql.SQL('(data ->> %s) collate "C" {} %s').format(operator), [field, value]
    return sql.SQL("(data -> %s) {} %s::jsonb").format(operator), [field, json.dumps(value)]


def build_select(
    path: str,
    filters: list[Filter] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int | None = None,
) -> tuple[sql.Composed, list[Any]]:
    """Query and parameters for Repository.list (pure; unit-tested without a database)."""
    clauses: list[sql.Composable] = [sql.SQL("collection = %s")]
    params: list[Any] = [path]
    for field, op, value in filters or []:
        name = _field(field)
        condition, values = _condition(name, op, value)
        clauses.append(sql.SQL("(data ? %s) and {}").format(condition))
        params += [name, *values]
    parts = [sql.SQL("select id, data from documents where {}").format(sql.SQL(" and ").join(clauses))]
    if order_by:
        name = _field(order_by)
        direction = sql.SQL("desc" if descending else "asc")
        parts.append(
            sql.SQL(
                " order by case when jsonb_typeof(data -> %s) = 'number' then (data ->> %s)::numeric end"
                ' {d} nulls last, (data ->> %s) collate "C" {d}'
            ).format(d=direction)
        )
        params += [name, name, name]
    if limit:
        parts.append(sql.SQL(" limit %s"))
        params.append(int(limit))
    return sql.Composed(parts), params


class PostgresRepository:
    def __init__(self, dsn: str, ensure_schema: bool = True) -> None:
        # prepare_threshold=None keeps it compatible with Supabase's connection pooler.
        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": tuple_row},
            open=True,
        )
        if ensure_schema:
            with self._pool.connection() as conn:
                conn.execute(SCHEMA)

    def close(self) -> None:
        self._pool.close()

    def create(self, path: str, data: dict[str, Any], doc_id: str | None = None) -> str:
        doc_id = doc_id or uuid.uuid4().hex
        self.set(path, doc_id, data)
        return doc_id

    def set(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "insert into documents (collection, id, data) values (%s, %s, %s) "
                "on conflict (collection, id) do update set data = excluded.data, updated_at = now()",
                [path, doc_id, Jsonb(data)],
            )

    def get(self, path: str, doc_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select data from documents where collection = %s and id = %s", [path, doc_id]
            ).fetchone()
        return {**row[0], "id": doc_id} if row else None

    def update(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            cur = conn.execute(
                "update documents set data = data || %s, updated_at = now() "
                "where collection = %s and id = %s",
                [Jsonb(data), path, doc_id],
            )
            if cur.rowcount == 0:
                raise KeyError(f"{path}/{doc_id} not found")

    def delete(self, path: str, doc_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("delete from documents where collection = %s and id = %s", [path, doc_id])

    def list(
        self,
        path: str,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql, params = build_select(path, filters, order_by, descending, limit)
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{**data, "id": doc_id} for doc_id, data in rows]
