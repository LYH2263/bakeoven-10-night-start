"""End-to-end API behaviour for previous-night fermentation, on SQLite."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Batch, Oven, Product
from app.services.oven_engine import DAY_OPEN


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = TestingSession()
    # Realistic overnight loaf: ~8h40 ferment, 40m bake — crosses 00:00 and is
    # still proofing after the 08:00 open.
    overnight = Product(name="慢熟乡村", ferment_min=520, bake_min=40)
    # No-ferment product with a short bake.
    brownie = Product(name="布朗尼", ferment_min=0, bake_min=30)
    oven = Oven(label="一层 1 号炉", capacity_note="盘炉")
    db.add_all([overnight, brownie, oven])
    db.commit()
    db.refresh(overnight)
    db.refresh(brownie)
    db.refresh(oven)
    ids = (overnight.id, brownie.id, oven.id)
    db.close()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, ids, TestingSession
    app.dependency_overrides.clear()


def test_night_batch_created_and_persisted(client):
    c, (pid, _bid, oid), Session = client
    # 23:30 previous night (-30): ferment [-30,490), bake [490,530), done after open.
    r = c.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": oid, "start_min": -30, "start_day_offset": -1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_min"] == -30
    assert body["start_day_offset"] == -1
    assert body["night_start"] is True
    assert body["ferment_end"] == 490
    assert body["bake_end"] == 530
    # Persisted across sessions (leave the page and come back).
    with Session() as s:
        row = s.scalar(select(Batch).where(Batch.id == body["id"]))
        assert row.start_day_offset == -1
        assert row.start_min == -30


def test_night_batch_rejected_when_baking_ends_before_open(client):
    c, (pid, _bid, oid), _ = client
    # total 560; starting at -7h ends at 140 (02:20), before the 08:00 open.
    r = c.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": oid, "start_min": -7 * 60, "start_day_offset": -1},
    )
    assert r.status_code == 409
    assert "开门" in r.json()["detail"]


def test_night_ferment_overlap_with_today_batch_rejected(client):
    c, (_pid, bid, oid), _ = client
    # Same-day brownie bakes [480,510) right at open.
    r0 = c.post("/api/batches", json={"product_id": bid, "oven_id": oid, "start_min": 480})
    assert r0.status_code == 200, r0.text
    # Night loaf ferments [-30,490): its today-visible proof overlaps [480,490).
    r = c.post(
        "/api/batches",
        json={"product_id": _pid, "oven_id": oid, "start_min": -30, "start_day_offset": -1},
    )
    assert r.status_code == 409
    assert "重叠" in r.json()["detail"]


def test_negative_minute_requires_night_marker(client):
    c, (pid, _bid, oid), _ = client
    r = c.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": oid, "start_min": -30},
    )
    assert r.status_code == 422


def test_night_marker_requires_negative_minute(client):
    c, (pid, _bid, oid), _ = client
    r = c.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": oid, "start_min": 60, "start_day_offset": -1},
    )
    assert r.status_code == 422


def test_gantt_clips_night_batch_and_flags_it(client):
    c, (pid, _bid, oid), _ = client
    r = c.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": oid, "start_min": -30, "start_day_offset": -1},
    )
    assert r.status_code == 200, r.text
    blocks = c.get("/api/gantt").json()
    # Ferment [-30,490) clips to [0,490); bake [490,530) stays whole. No negatives.
    ferment = [b for b in blocks if b["phase"] == "ferment"]
    bake = [b for b in blocks if b["phase"] == "bake"]
    assert len(ferment) == 1 and len(bake) == 1
    assert ferment[0]["start_min"] == 0 and ferment[0]["end_min"] == 490
    assert bake[0]["start_min"] == 490 and bake[0]["end_min"] == 530
    assert all(b["night_start"] for b in blocks)
    assert all(b["start_min"] >= 0 for b in blocks)


def test_same_day_batch_draws_full_segment(client):
    c, (_pid, bid, oid), _ = client
    r = c.post("/api/batches", json={"product_id": bid, "oven_id": oid, "start_min": 600})
    assert r.status_code == 200, r.text
    blocks = c.get("/api/gantt").json()
    # Brownie: no ferment block; bake [600,630) drawn in full, not night-flagged.
    bake = [b for b in blocks if b["phase"] == "bake"]
    assert bake[0]["start_min"] == 600 and bake[0]["end_min"] == 630
    assert bake[0]["night_start"] is False


def test_day_open_value():
    assert DAY_OPEN == 480
