from tests.conftest import MED, add_member


def test_create_and_list_medication(owner):
    c, _ = owner
    res = c.post("/api/medications", json=MED)
    assert res.status_code == 201
    med = res.json()
    assert med["status"] == "active"
    assert med["times"] == ["08:00", "20:00"]  # Sorted.
    assert [m["name"] for m in c.get("/api/medications").json()] == ["Metformin"]


def test_medication_validation(owner):
    c, _ = owner
    assert c.post("/api/medications", json={**MED, "times": ["25:00"]}).status_code == 422
    assert c.post("/api/medications", json={**MED, "times": ["08:00", "08:00"]}).status_code == 422
    assert c.post("/api/medications", json={**MED, "times": []}).status_code == 422
    assert c.post("/api/medications", json={**MED, "end_date": "2026-11-01"}).status_code == 422


def test_update_pause_and_delete(owner):
    c, _ = owner
    med_id = c.post("/api/medications", json=MED).json()["id"]
    updated = c.put(f"/api/medications/{med_id}", json={**MED, "dosage": "1000 mg", "paused": True})
    assert updated.json()["dosage"] == "1000 mg"
    assert updated.json()["status"] == "paused"
    assert c.delete(f"/api/medications/{med_id}").status_code == 204
    assert c.put(f"/api/medications/{med_id}", json=MED).status_code == 404


def test_family_cannot_edit_medications(app, owner):
    c, _ = owner
    family = add_member(c, app, "family", "son@example.com")
    assert family.post("/api/medications", json=MED).status_code == 403
    assert family.get("/api/medications").status_code == 200


def test_caretaker_changes_need_owner_approval_when_enabled(app, owner):
    c, _ = owner
    caretaker = add_member(c, app, "caretaker", "nurse@example.com")
    assert c.put("/api/profile/settings", json={"require_approval": True}).status_code == 200

    med = caretaker.post("/api/medications", json=MED).json()
    assert med["status"] == "pending"
    # Caretakers cannot approve their own changes.
    assert caretaker.post(f"/api/medications/{med['id']}/approve").status_code == 403

    approved = c.post(f"/api/medications/{med['id']}/approve")
    assert approved.json()["status"] == "active"
    assert c.post(f"/api/medications/{med['id']}/approve").status_code == 409


def test_caretaker_changes_apply_directly_when_approval_off(app, owner):
    c, _ = owner
    caretaker = add_member(c, app, "caretaker", "nurse@example.com")
    assert caretaker.post("/api/medications", json=MED).json()["status"] == "active"


def test_changes_are_recorded_in_activity_log(owner):
    c, _ = owner
    c.post("/api/medications", json=MED)
    actions = [entry["action"] for entry in c.get("/api/activity").json()]
    assert actions[0] == "medication.created"
    assert "profile.created" in actions
