"""이벤트 생성기 진입점.

동작:
  1. 시드 단계: SEED_COUNT 만큼 과거 SEED_DAYS 일에 분포된 이벤트 생성
  2. 스트림 단계: 무한 루프, 매초 STREAM_MIN_RPS ~ STREAM_MAX_RPS 건 생성

저장:
  PostgreSQL events 테이블에 배치 INSERT (BATCH_SIZE 단위).

환경변수 (없으면 기본값 사용):
  SEED_COUNT        시드 건수            (기본 5000)
  USER_COUNT        가상 유저 수          (기본 100)
  SEED_DAYS         시드 분포 기간(일)    (기본 7)
  STREAM_MIN_RPS    초당 최소 이벤트 수    (기본 2)
  STREAM_MAX_RPS    초당 최대 이벤트 수    (기본 5)
  BATCH_SIZE        배치 적재 단위        (기본 1000)
  POSTGRES_HOST     DB 호스트            (기본 localhost)
  POSTGRES_PORT     DB 포트              (기본 5432)
  POSTGRES_USER     DB 사용자             (기본 eventuser)
  POSTGRES_PASSWORD DB 비밀번호           (기본 changeme)
  POSTGRES_DB       DB 이름              (기본 eventdb)
"""

from __future__ import annotations

import os
import random
import signal
import time
import uuid
from datetime import datetime, timedelta, timezone

import db
from events import generate_event


# ============================================================
# 환경변수 로딩
# ============================================================
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(
            f"환경변수 {name} 은 정수여야 합니다 (실제 값: {raw!r})"
        ) from e


SEED_COUNT     = _env_int("SEED_COUNT", 5000)
USER_COUNT     = _env_int("USER_COUNT", 100)
SEED_DAYS      = _env_int("SEED_DAYS", 7)
STREAM_MIN_RPS = _env_int("STREAM_MIN_RPS", 2)
STREAM_MAX_RPS = _env_int("STREAM_MAX_RPS", 5)
BATCH_SIZE     = _env_int("BATCH_SIZE", 1000)


# ============================================================
# 보조 함수
# ============================================================
def _random_user_id() -> int:
    return random.randint(1, USER_COUNT)


def _random_session_id() -> str:
    # 사용자 세션은 16자 hex (events.session_id VARCHAR(64) 안에 충분히 들어감)
    return uuid.uuid4().hex[:16]


def _random_past_time(within_days: int) -> datetime:
    now = datetime.now(timezone.utc)
    delta_seconds = random.randint(0, within_days * 24 * 3600)
    return now - timedelta(seconds=delta_seconds)


# ============================================================
# 단계별 실행
# ============================================================
def _seed_phase(conn) -> None:
    print(f"[seed] {SEED_COUNT}건 생성 시작", flush=True)
    buffer: list[dict] = []
    for _ in range(SEED_COUNT):
        buffer.append(
            generate_event(
                user_id=_random_user_id(),
                session_id=_random_session_id(),
                when=_random_past_time(SEED_DAYS),
            )
        )
        if len(buffer) >= BATCH_SIZE:
            db.write_batch(conn, buffer)
            buffer.clear()
    if buffer:
        db.write_batch(conn, buffer)
        buffer.clear()
    print("[seed] 완료", flush=True)


def _stream_phase(conn) -> None:
    print(
        f"[stream] 초당 {STREAM_MIN_RPS}~{STREAM_MAX_RPS}건 생성 시작 (Ctrl+C 로 종료)",
        flush=True,
    )
    while True:
        rps = random.randint(STREAM_MIN_RPS, STREAM_MAX_RPS)
        buffer = [
            generate_event(
                user_id=_random_user_id(),
                session_id=_random_session_id(),
                when=datetime.now(timezone.utc),
            )
            for _ in range(rps)
        ]
        db.write_batch(conn, buffer)
        time.sleep(1)


def main() -> None:
    # 다운스트림(예: | head)이 파이프를 닫으면 SIGPIPE 발생.
    # 기본 처리(SIG_DFL)로 두면 Python 이 BrokenPipeError 트레이스 없이 즉시 종료한다.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    conn = db.connect()
    try:
        _seed_phase(conn)
        _stream_phase(conn)
    except (KeyboardInterrupt, BrokenPipeError):
        print("[main] 종료 시그널 수신 — 깔끔히 종료합니다.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
