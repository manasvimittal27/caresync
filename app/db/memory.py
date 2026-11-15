"""In-memory repository used for local development and tests."""

import copy
import operator
import threading
import uuid
from typing import Any

from app.db.base import Filter

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "in": lambda value, options: value in options,
}


class InMemoryRepository:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def create(self, path: str, data: dict[str, Any], doc_id: str | None = None) -> str:
        doc_id = doc_id or uuid.uuid4().hex
        self.set(path, doc_id, data)
        return doc_id

    def set(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._data.setdefault(path, {})[doc_id] = copy.deepcopy(data)

    def get(self, path: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._data.get(path, {}).get(doc_id)
        return {**copy.deepcopy(doc), "id": doc_id} if doc is not None else None

    def update(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            doc = self._data.get(path, {}).get(doc_id)
            if doc is None:
                raise KeyError(f"{path}/{doc_id} not found")
            doc.update(copy.deepcopy(data))

    def delete(self, path: str, doc_id: str) -> None:
        with self._lock:
            self._data.get(path, {}).pop(doc_id, None)

    def list(
        self,
        path: str,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        docs = [{**copy.deepcopy(d), "id": i} for i, d in self._data.get(path, {}).items()]
        for field, op, value in filters or []:
            docs = [d for d in docs if field in d and _OPS[op](d[field], value)]
        if order_by:
            docs.sort(key=lambda d: d.get(order_by) or "", reverse=descending)
        return docs[:limit] if limit else docs
