"""generator.db + events 통합 테스트.

testcontainers 로 실제 PostgreSQL 컨테이너를 띄워서
스키마 적용 → batch INSERT → 집계까지 end-to-end 검증한다.

mock 대신 실 DB 를 쓰는 이유: SQL 제약, JSONB 어댑팅, 트랜잭션 롤백 같은
DB-side 동작은 mock 으로 검증하면 prod 와 divergence 위험이 있다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

import db
import events


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "init" / "01_schema.sql"


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="session")
def pg_url():
    """세션 한 번만 띄우는 PostgreSQL 컨테이너 + 스키마 적용.

    psycopg3 호환을 위해 sqlalchemy 풍 URL 대신 직접 dsn 조립한다.
    """
    with PostgresContainer("postgres:16-alpine") as postgres:
        host = postgres.get_container_host_ip()
        port = postgres.get_exposed_port(5432)
        url = (
            f"postgresql://{postgres.username}:{postgres.password}"
            f"@{host}:{port}/{postgres.dbname}"
        )

        # 스키마 적용 (첫 기동 시 한 번)
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_PATH.read_text())
            conn.commit()

        yield url


@pytest.fixture
def conn(pg_url):
    """매 테스트마다 깨끗한 events 테이블 + 새 연결."""
    with psycopg.connect(pg_url, autocommit=False) as c:
        with c.cursor() as cur:
            cur.execute("TRUNCATE events;")
        c.commit()
        yield c


# ============================================================
# Helper
# ============================================================
def _make_event(event_type: str | None = None) -> dict:
    """`events.generate_event` 한 건 생성. 특정 타입 강제 시 가중치 분포 때문에 재시도."""
    def _one() -> dict:
        return events.generate_event(
            user_id=1,
            session_id="sess-test",
            when=datetime.now(timezone.utc),
        )

    if event_type is None:
        return _one()

    for _ in range(1000):
        event = _one()
        if event["event_type"] == event_type:
            return event
    pytest.fail(f"{event_type} 타입을 1000회 안에 생성하지 못했습니다.")


# ============================================================
# 통합 테스트 케이스
# ============================================================
def test_write_single_event(conn):
    """단일 이벤트 적재 후 SELECT 로 확인."""
    event = _make_event()
    db.write_batch(conn, [event])

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events;")
        assert cur.fetchone()[0] == 1


def test_write_batch_1000(conn):
    """배치 1000건 적재 → executemany 가 실제로 1000건 전부 들어가는지."""
    batch = [_make_event() for _ in range(1000)]
    db.write_batch(conn, batch)

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events;")
        assert cur.fetchone()[0] == 1000


def test_jsonb_properties_round_trip(conn):
    """JSONB 어댑터가 dict → JSONB → dict 까지 보존하는지 확인."""
    event = _make_event("purchase")
    db.write_batch(conn, [event])

    with conn.cursor() as cur:
        cur.execute("SELECT properties FROM events;")
        stored = cur.fetchone()[0]

    assert "product_id" in stored
    assert "amount" in stored
    assert isinstance(stored["amount"], int)
    # dict 가 통째로 보존되어야 함
    assert stored == event["properties"]


def test_aggregation_distribution(conn):
    """5000건 적재 후 80/15/5 가중치가 실제 분포까지 일관되는지 (end-to-end)."""
    batch = [_make_event() for _ in range(5000)]
    db.write_batch(conn, batch)

    with conn.cursor() as cur:
        cur.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type;")
        counts = dict(cur.fetchall())

    total = sum(counts.values())
    assert total == 5000

    ratios = {k: v / total for k, v in counts.items()}
    # 5000건 샘플 → ±5%p 허용
    assert abs(ratios.get("page_view", 0) - 0.80) < 0.05
    assert abs(ratios.get("purchase",  0) - 0.15) < 0.05
    assert abs(ratios.get("error",     0) - 0.05) < 0.05


def test_check_constraint_violation_rolls_back(conn):
    """허용되지 않은 event_type 적재 시 IntegrityError + 테이블 0건 유지."""
    invalid_event = _make_event()
    invalid_event["event_type"] = "invalid_type"

    with pytest.raises(psycopg.errors.CheckViolation):
        db.write_batch(conn, [invalid_event])

    # write_batch 가 rollback 후 re-raise 하므로 데이터가 0건이어야 함
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events;")
        assert cur.fetchone()[0] == 0
