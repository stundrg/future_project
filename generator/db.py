"""PostgreSQL 적재 모듈.

이벤트 dict 리스트를 받아 events 테이블에 배치 INSERT 한다.
연결 시 짧은 재시도를 둬서 docker-compose 환경에서 DB가 늦게 뜨는 경우에 대응한다.
"""

from __future__ import annotations

import os
import time
from typing import Iterable

import psycopg
from psycopg.types.json import Jsonb


_INSERT_SQL = """
INSERT INTO events (
    event_id, event_type, user_id, session_id, created_at,
    ip_address, user_agent, properties
)
VALUES (
    %(event_id)s, %(event_type)s, %(user_id)s, %(session_id)s, %(created_at)s,
    %(ip_address)s, %(user_agent)s, %(properties)s
)
"""


def _build_dsn() -> str:
    """환경변수로부터 PostgreSQL 연결 문자열 생성."""
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"user={os.getenv('POSTGRES_USER', 'eventuser')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'changeme')} "
        f"dbname={os.getenv('POSTGRES_DB', 'eventdb')}"
    )


def connect(retries: int = 5, delay_seconds: float = 1.0) -> psycopg.Connection:
    """DB에 연결. docker-compose 환경에서 DB가 늦게 뜰 수 있어 짧은 재시도를 둔다.

    재시도 소진 시 RuntimeError 발생.
    """
    dsn = _build_dsn()
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg.connect(dsn, autocommit=False)
            print(f"[db] PostgreSQL 연결 성공 (attempt {attempt})", flush=True)
            return conn
        except psycopg.OperationalError as e:
            last_error = e
            print(
                f"[db] 연결 실패 (attempt {attempt}/{retries}): {e}. "
                f"{delay_seconds}s 후 재시도",
                flush=True,
            )
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"PostgreSQL 연결 실패 (재시도 {retries}회 소진): {last_error}"
    )


def write_batch(conn: psycopg.Connection, events: Iterable[dict]) -> None:
    """이벤트 리스트를 단일 트랜잭션으로 배치 INSERT 한다.

    실패 시 롤백하고 예외를 다시 raise (호출자가 결정하도록).
    """
    rows = [_prepare_row(e) for e in events]
    if not rows:
        return
    try:
        with conn.cursor() as cur:
            cur.executemany(_INSERT_SQL, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _prepare_row(event: dict) -> dict:
    """event dict 를 INSERT 파라미터 형태로 정리.

    properties 는 psycopg 의 Jsonb 어댑터로 감싸 JSONB 컬럼에 안전히 들어가도록 한다.
    """
    return {
        **event,
        "properties": Jsonb(event["properties"]),
    }
