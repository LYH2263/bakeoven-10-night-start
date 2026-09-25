"""API 级测试：夜间发酵（前一日开工）批次的登记、拒绝与展示。

用 sqlite 内存库覆盖 get_db；TestClient 不以上下文管理器运行，
因此不会触发 lifespan（不会去连生产 Postgres）。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Product
from app.services.seed import seed_if_empty

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_if_empty(db)
    db.close()
    yield


def _add_slow_bread() -> int:
    """隔夜发酵产品：发酵 600 分钟 + 烘烤 60 分钟，返回产品 id。"""
    db = TestingSessionLocal()
    p = Product(name="隔夜酸种", ferment_min=600, bake_min=60)
    db.add(p)
    db.commit()
    pid = p.id
    db.close()
    return pid


def test_seed_bo0900_untouched_by_overnight_rules():
    rows = client.get("/api/batches").json()
    bo = next(r for r in rows if r["code"] == "BO-0900")
    assert bo["start_min"] == 9 * 60
    assert bo["prev_day"] is False
    blocks = [b for b in client.get("/api/gantt").json() if b["code"] == "BO-0900"]
    assert blocks and all(b["prev_day"] is False for b in blocks)
    assert min(b["start_min"] for b in blocks) == 9 * 60  # 当日段画全段


def test_create_overnight_prev_day_marker_persists():
    pid = _add_slow_bread()
    resp = client.post(
        "/api/batches",
        json={"product_id": pid, "oven_id": 3, "start_min": 22 * 60, "prev_day": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prev_day"] is True
    assert body["start_min"] == -120  # 前一日 22:00
    # 离开再进来仍在：重新拉取列表，夜间标记与开工分钟保持
    again = client.get("/api/batches").json()
    mine = next(r for r in again if r["id"] == body["id"])
    assert mine["prev_day"] is True
    assert mine["start_min"] == -120


def test_create_overnight_negative_minutes():
    pid = _add_slow_bread()
    resp = client.post("/api/batches", json={"product_id": pid, "oven_id": 3, "start_min": -120})
    assert resp.status_code == 200, resp.text
    assert resp.json()["prev_day"] is True


def test_overnight_bake_end_before_open_rejected():
    # 布朗尼 0+30 分钟，前一日 23:30 开工 → 当日 0:00 烤完，早于 08:00 开门
    resp = client.post("/api/batches", json={"product_id": 3, "oven_id": 3, "start_min": -30})
    assert resp.status_code == 409
    assert "开门" in resp.json()["detail"]
    logs = client.get("/api/conflicts").json()
    assert any("开门" in c["detail"] for c in logs)


def test_overnight_ferment_overlap_same_day_rejected():
    pid = _add_slow_bread()
    r1 = client.post("/api/batches", json={"product_id": pid, "oven_id": 3, "start_min": 360})
    assert r1.status_code == 200  # 当日 6:00 起占 [360, 1020)
    # 夜间批发酵段 [-120, 480) 跨过 0 点，与当日批次重叠 → 拒绝
    r2 = client.post("/api/batches", json={"product_id": pid, "oven_id": 3, "start_min": -120})
    assert r2.status_code == 409


def test_same_day_batch_unchanged():
    resp = client.post("/api/batches", json={"product_id": 1, "oven_id": 3, "start_min": 600})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prev_day"] is False
    assert body["start_min"] == 600


def test_gantt_clips_overnight_to_after_midnight_and_marks():
    pid = _add_slow_bread()
    client.post("/api/batches", json={"product_id": pid, "oven_id": 3, "start_min": -120})
    blocks = client.get("/api/gantt").json()
    mine = [b for b in blocks if b["oven_id"] == 3]
    assert mine and all(b["prev_day"] is True for b in mine)
    assert all(b["start_min"] >= 0 for b in mine)  # 只画 0 点后仍占的部分
    ferment = next(b for b in mine if b["phase"] == "ferment")
    assert (ferment["start_min"], ferment["end_min"]) == (0, 480)
    bake = next(b for b in mine if b["phase"] == "bake")
    assert (bake["start_min"], bake["end_min"]) == (480, 540)


def test_windows_use_full_overnight_interval():
    pid = _add_slow_bread()
    client.post("/api/batches", json={"product_id": pid, "oven_id": 3, "start_min": -120})
    rows = client.get("/api/windows", params={"product_id": 1}).json()  # 乡村欧包 75 分钟
    w3 = next(r for r in rows if r["oven_id"] == 3)
    # 夜间批完整区间占到 9:00，可开工从 540 起，而不是 8:00
    assert w3["start_min"] == 540
