"""Storage abstraction.

Routes and services depend on this small interface rather than on Firestore
directly, which keeps business logic testable with an in-memory implementation.

Collection paths use Firestore's slash form, e.g. ``elders/{id}/medications``.
Every returned document includes its ``id``.
"""

from typing import Any, Protocol

Filter = tuple[str, str, Any]


class Repository(Protocol):
    def create(self, path: str, data: dict[str, Any], doc_id: str | None = None) -> str: ...

    def set(self, path: str, doc_id: str, data: dict[str, Any]) -> None: ...

    def get(self, path: str, doc_id: str) -> dict[str, Any] | None: ...

    def update(self, path: str, doc_id: str, data: dict[str, Any]) -> None: ...

    def delete(self, path: str, doc_id: str) -> None: ...

    def list(
        self,
        path: str,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
