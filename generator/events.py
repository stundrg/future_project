"""이벤트 생성 함수.

이벤트 타입(page_view / purchase / error)별 properties를 만들고,
공통 필드와 함께 단일 dict로 반환한다.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime

from faker import Faker

fake = Faker()

# 이벤트 타입별 발생 비율 (실제 서비스 분포 흉내)
EVENT_TYPE_WEIGHTS: list[tuple[str, int]] = [
    ("page_view", 80),
    ("purchase",  15),
    ("error",      5),
]

_EVENT_TYPES = [t for t, _ in EVENT_TYPE_WEIGHTS]
_WEIGHTS     = [w for _, w in EVENT_TYPE_WEIGHTS]


# ============================================================
# 타입별 properties 생성
# ============================================================
def _properties_for_page_view() -> dict:
    return {
        "path": fake.uri_path(),
        "referrer": random.choice(["/", "/home", "/products", "/search", None]),
    }


def _properties_for_purchase() -> dict:
    return {
        "product_id": f"P-{random.randint(1, 200):04d}",
        "amount": random.choice([9900, 19900, 29900, 49900, 99900, 199000]),
        "currency": "KRW",
    }


_ERROR_CODES = ["400", "401", "403", "404", "500", "502", "503"]
_ERROR_MESSAGES = {
    "400": "Bad Request",
    "401": "Unauthorized",
    "403": "Forbidden",
    "404": "Not Found",
    "500": "Internal Server Error",
    "502": "Bad Gateway",
    "503": "Service Unavailable",
}


def _properties_for_error() -> dict:
    code = random.choice(_ERROR_CODES)
    return {
        "error_code": code,
        "message": _ERROR_MESSAGES[code],
        "path": fake.uri_path(),
    }


_PROPERTIES_BUILDERS = {
    "page_view": _properties_for_page_view,
    "purchase":  _properties_for_purchase,
    "error":     _properties_for_error,
}


# ============================================================
# 공개 API
# ============================================================
def pick_event_type() -> str:
    """가중치를 적용한 이벤트 타입 랜덤 선택."""
    return random.choices(_EVENT_TYPES, weights=_WEIGHTS, k=1)[0]


def generate_event(*, user_id: int, session_id: str, when: datetime) -> dict:
    """이벤트 한 건을 생성해 dict로 반환한다.

    공통 필드는 명시적 컬럼으로, 타입별 가변 필드는 properties로 담는다.
    """
    event_type = pick_event_type()
    return {
        "event_id":    str(uuid.uuid4()),
        "event_type":  event_type,
        "user_id":     user_id,
        "session_id":  session_id,
        "created_at":  when.isoformat(),
        "ip_address":  fake.ipv4(),
        "user_agent":  fake.user_agent(),
        "properties":  _PROPERTIES_BUILDERS[event_type](),
    }
