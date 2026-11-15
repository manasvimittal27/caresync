"""Firestore-backed repository (Google Cloud Firestore, Native mode)."""

from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.db.base import Filter


class FirestoreRepository:
    def __init__(self, project: str | None = None) -> None:
        # On Cloud Run, credentials come from the service account automatically.
        self._client = firestore.Client(project=project)

    def _col(self, path: str) -> firestore.CollectionReference:
        return self._client.collection(path)

    def create(self, path: str, data: dict[str, Any], doc_id: str | None = None) -> str:
        ref = self._col(path).document(doc_id) if doc_id else self._col(path).document()
        ref.set(data)
        return ref.id

    def set(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        self._col(path).document(doc_id).set(data)

    def get(self, path: str, doc_id: str) -> dict[str, Any] | None:
        snap = self._col(path).document(doc_id).get()
        return {**snap.to_dict(), "id": snap.id} if snap.exists else None

    def update(self, path: str, doc_id: str, data: dict[str, Any]) -> None:
        self._col(path).document(doc_id).update(data)

    def delete(self, path: str, doc_id: str) -> None:
        self._col(path).document(doc_id).delete()

    def list(
        self,
        path: str,
        filters: list[Filter] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query: Any = self._col(path)
        for field, op, value in filters or []:
            query = query.where(filter=FieldFilter(field, op, value))
        if order_by:
            direction = firestore.Query.DESCENDING if descending else firestore.Query.ASCENDING
            query = query.order_by(order_by, direction=direction)
        if limit:
            query = query.limit(limit)
        return [{**snap.to_dict(), "id": snap.id} for snap in query.stream()]
