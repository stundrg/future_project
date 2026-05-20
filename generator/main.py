"""이벤트 생성기 진입점.

동작:
  1. 시드 단계: SEED_COUNT 만큼 과거 SEED_DAYS 일에 분포된 이벤트 생성
  2. 스트림 단계: 무한 루프, 매초 STREAM_MIN_RPS ~ STREAM_MAX_RPS 건 생성

출력:
  stdout 에 한 줄당 JSON 한 건. PR 4에서 PostgreSQL 적재로 전환된다.

환경변수 (없으면 기본값 사용):
  SEED_COUNT      시드 건수            (기본 5000)
  USER_COUNT      가상 유저 수          (기본 100)
  SEED_DAYS       시드 분포 기간(일)    (기본 7)
  STREAM_MIN_RPS  초당 최소 이벤트 수    (기본 2)
  STREAM_MAX_RPS  초당 최대 이벤트 수    (기본 5)
"""

from __future__ import annotations

import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from events import generate_event


# ============================================================
# 환경변수 로딩
# ============================================================
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


SEED_COUNT     = _env_int("SEED_COUNT", 5000)
USER_COUNT     = _env_int("USER_COUNT", 100)
SEED_DAYS      = _env_int("SEED_DAYS", 7)
STREAM_MIN_RPS = _env_int("STREAM_MIN_RPS", 2)
STREAM_MAX_RPS = _env_int("STREAM_MAX_RPS", 5)


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


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ============================================================
# 단계별 실행
# ============================================================
def _seed_phase() -> None:
    for _ in range(SEED_COUNT):
        event = generate_event(
            user_id=_random_user_id(),
            session_id=_random_session_id(),
            when=_random_past_time(SEED_DAYS),
        )
        _emit(event)


def _stream_phase() -> None:
    while True:
        rps = random.randint(STREAM_MIN_RPS, STREAM_MAX_RPS)
        for _ in range(rps):
            event = generate_event(
                user_id=_random_user_id(),
                session_id=_random_session_id(),
                when=datetime.now(timezone.utc),
            )
            _emit(event)
        time.sleep(1)


def main() -> None:
    # 다운스트림(예: | head)이 파이프를 닫으면 SIGPIPE 발생.
    # 기본 처리(SIG_DFL)로 두면 Python이 BrokenPipeError 트레이스 없이 즉시 종료한다.
    # Windows는 SIGPIPE가 없어서 hasattr 가드.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    try:
        _seed_phase()
        _stream_phase()
    except (KeyboardInterrupt, BrokenPipeError):
        # Windows 안전망 (Unix 는 위 SIGPIPE 처리로 이미 종료됨)
        pass


if __name__ == "__main__":
    main()
