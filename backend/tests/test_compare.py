import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.compare import build_compare_diff, latest_metrics_by_name
from app.cqrs import complete_run, record_metric, start_run
from app.database import Base, get_db
from app.main import app


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # JSONB not available on SQLite — remap via create_all with JSON
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # For SQLite tests, compile JSONB as JSON
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(_type, compiler, **kw):
        return "JSON"

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _completed_run(db, *, dataset: str, commit: str, metrics: list[tuple[str, float, int]]):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="n1",
        dataset_content_sha256=sha(dataset),
        code_commit_sha=commit,
        description=None,
        run_id=uuid4(),
    )
    for name, value, step in metrics:
        run = record_metric(
            db,
            run_id=run.id,
            actor="researcher",
            name=name,
            value=value,
            step=step,
            expected_version=run.version,
        )
    return complete_run(
        db,
        run_id=run.id,
        actor="researcher",
        result_summary="done",
        expected_version=run.version,
    )


def test_latest_metrics_by_name_keeps_max_step():
    metrics = [
        {"name": "acc", "value": 0.7, "step": 1},
        {"name": "acc", "value": 0.9, "step": 3},
        {"name": "acc", "value": 0.8, "step": 2},
        {"name": "loss", "value": 1.2, "step": 1},
        {"value": 9.9, "step": 1},  # 无 name,忽略
    ]
    latest = latest_metrics_by_name(metrics)
    assert latest["acc"]["value"] == 0.9
    assert latest["acc"]["step"] == 3
    assert latest["loss"]["value"] == 1.2
    assert len(latest) == 2


def test_compare_diff_flags_fingerprints_and_metric_name_sets(db):
    run_a = _completed_run(
        db,
        dataset="ds-a",
        commit="aaa1111",
        metrics=[("tm_score", 0.81, 2), ("tm_score", 0.72, 1), ("loss", 0.4, 1)],
    )
    run_b = _completed_run(
        db,
        dataset="ds-b",
        commit="bbb2222",
        metrics=[("hit_rate", 0.12, 1), ("loss", 0.7, 1)],
    )

    diff = build_compare_diff(run_a, run_b)

    assert diff["code_commit_same"] is False
    assert diff["dataset_same"] is False
    assert diff["metric_names_only_a"] == ["tm_score"]
    assert diff["metric_names_only_b"] == ["hit_rate"]

    rows = {r["name"]: r for r in diff["metrics"]}
    assert rows["tm_score"]["in_a"] is True and rows["tm_score"]["in_b"] is False
    assert rows["tm_score"]["a_value"] == 0.81  # 取 step 最大的最新值
    assert rows["hit_rate"]["in_b"] is True and rows["hit_rate"]["in_a"] is False
    assert rows["loss"]["in_a"] and rows["loss"]["in_b"]
    assert rows["loss"]["value_differs"] is True


def test_compare_diff_same_fingerprints_no_set_difference(db):
    run_a = _completed_run(db, dataset="ds-x", commit="abc1234", metrics=[("acc", 0.9, 1)])
    run_b = _completed_run(db, dataset="ds-x", commit="abc1234", metrics=[("acc", 0.9, 1)])

    diff = build_compare_diff(run_a, run_b)

    assert diff["code_commit_same"] is True
    assert diff["dataset_same"] is True
    assert diff["metric_names_only_a"] == []
    assert diff["metric_names_only_b"] == []
    assert diff["metrics"][0]["value_differs"] is False


def test_compare_endpoint_readonly_for_auditor(db):
    run_a = _completed_run(db, dataset="ds-a", commit="aaa1111", metrics=[("acc", 0.9, 1)])
    run_b = _completed_run(db, dataset="ds-b", commit="bbb2222", metrics=[("f1", 0.5, 1)])

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        token = create_access_token("auditor", "auditor")
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(f"/api/compare?run_a={run_a.id}&run_b={run_b.id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["a"]["run_id"] == str(run_a.id)
        assert body["b"]["run_id"] == str(run_b.id)
        assert body["diff"]["dataset_same"] is False
        assert body["diff"]["code_commit_same"] is False
        assert body["diff"]["metric_names_only_a"] == ["acc"]
        assert body["diff"]["metric_names_only_b"] == ["f1"]

        # 未登录不可读
        assert client.get(f"/api/compare?run_a={run_a.id}&run_b={run_b.id}").status_code == 401
        # Run 不存在 → 404
        assert (
            client.get(f"/api/compare?run_a={run_a.id}&run_b={uuid4()}", headers=headers).status_code
            == 404
        )
    finally:
        app.dependency_overrides.clear()
