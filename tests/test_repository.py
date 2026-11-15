"""Repository contract: the same behaviour from the in-memory and Postgres stores."""

import pytest

from app.db.postgres import build_select


def test_create_get_update_delete(repo):
    doc_id = repo.create("things", {"name": "a", "n": 1})
    assert repo.get("things", doc_id) == {"id": doc_id, "name": "a", "n": 1}
    repo.update("things", doc_id, {"n": 2, "extra": True})
    assert repo.get("things", doc_id)["n"] == 2 and repo.get("things", doc_id)["extra"] is True
    repo.delete("things", doc_id)
    assert repo.get("things", doc_id) is None


def test_set_replaces_document(repo):
    repo.set("things", "x", {"a": 1, "b": 2})
    repo.set("things", "x", {"a": 3})
    assert repo.get("things", "x") == {"id": "x", "a": 3}


def test_update_missing_raises(repo):
    with pytest.raises(KeyError):
        repo.update("things", "missing", {"a": 1})


def test_filters_and_ordering(repo):
    repo.set("e/1/logs", "a", {"date": "2026-11-14", "active": True, "seq": 30, "email": "a@x.co"})
    repo.set("e/1/logs", "b", {"date": "2026-11-15", "active": False, "seq": 5, "email": "b@x.co"})
    repo.set("e/1/logs", "c", {"date": "2026-11-16", "active": True, "seq": 100, "email": "c@x.co"})
    repo.set("e/2/logs", "z", {"date": "2026-11-15", "active": True, "seq": 1})  # Other collection.

    ids = lambda docs: [d["id"] for d in docs]  # noqa: E731
    assert ids(repo.list("e/1/logs", [("date", ">=", "2026-11-15")], order_by="date")) == ["b", "c"]
    assert ids(repo.list("e/1/logs", [("active", "==", True)], order_by="date")) == ["a", "c"]
    assert ids(repo.list("e/1/logs", [("email", "==", "b@x.co")])) == ["b"]
    # Numbers sort numerically (5 < 30 < 100), not as text.
    assert ids(repo.list("e/1/logs", order_by="seq", descending=True)) == ["c", "a", "b"]
    assert ids(repo.list("e/1/logs", order_by="seq", limit=2)) == ["b", "a"]
    assert repo.list("e/1/logs", [("missing_field", "==", "x")]) == []


def test_timestamps_compare_chronologically(repo):
    repo.set("appts", "late", {"starts_at": "2026-11-20T05:30:00Z"})
    repo.set("appts", "early", {"starts_at": "2026-11-09T23:00:00Z"})
    found = repo.list("appts", [("starts_at", ">=", "2026-11-15T00:00:00Z")], order_by="starts_at")
    assert [d["id"] for d in found] == ["late"]


def test_unicode_and_quotes_round_trip(repo):
    data = {"name": "Dr. O'Brien — कार्डियोलॉजी", "notes": 'Bring "ECG" report; DROP TABLE x;'}
    repo.set("appts", "u", data)
    assert repo.get("appts", "u") == {"id": "u", **data}


@pytest.mark.parametrize("bad", ["name; drop table documents", "Name", "a-b", "x" * 70, ""])
def test_field_names_are_validated(bad):
    with pytest.raises(ValueError):
        build_select("things", [(bad, "==", "x")])


def test_values_are_always_bound_parameters():
    query, params = build_select(
        "e/1/meds", [("name", "==", "x'); drop table documents; --")], "name", True, 5
    )
    assert "drop table" not in query.as_string(None)
    assert "x'); drop table documents; --" in params
