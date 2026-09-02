"""POST /api/demo/{seed,simulate,reset}."""

from sqlalchemy import select

from app.db.models import Case


def test_seed_creates_the_requested_count_with_at_least_one_hard_decline(client, db_session):
    resp = client.post("/api/demo/seed", json={"count": 12, "seed": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 12
    assert sum(body["byClass"].values()) == 12

    cases = db_session.execute(select(Case)).scalars().all()
    assert len(cases) == 12

    hard_declines = [c for c in cases if c.failure_class == "HARD_DECLINE"]
    assert hard_declines
    assert sum(c.demo_loose_prompt for c in hard_declines) == 1


def test_seed_is_reproducible_for_a_fixed_seed(client, db_session):
    r1 = client.post("/api/demo/seed", json={"count": 20, "seed": 42})
    by_class_1 = r1.json()["byClass"]

    client.post("/api/demo/reset")

    r2 = client.post("/api/demo/seed", json={"count": 20, "seed": 42})
    assert r2.json()["byClass"] == by_class_1


def test_simulate_recovers_some_fraction_of_open_cases(client, db_session):
    client.post("/api/demo/seed", json={"count": 40, "seed": 3})
    resp = client.post("/api/demo/simulate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["considered"] > 0
    assert 0 <= body["paid"] <= body["considered"]


def test_reset_clears_every_case_related_table(client, db_session):
    client.post("/api/demo/seed", json={"count": 5, "seed": 1})
    resp = client.post("/api/demo/reset")
    assert resp.status_code == 200
    assert db_session.execute(select(Case)).scalars().all() == []


def test_demo_routes_404_when_demo_mode_is_disabled(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.deps.settings.demo_mode", False)
    resp = client.post("/api/demo/seed", json={"count": 1})
    assert resp.status_code == 404
