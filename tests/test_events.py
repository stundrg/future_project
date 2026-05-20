"""이벤트 생성기 단위 테스트.

`generator/events.py` 의 공개 API (`generate_event`, `pick_event_type`)를 검증한다.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pytest

from events import generate_event, pick_event_type


REQUIRED_FIELDS = {
    "event_id",
    "event_type",
    "user_id",
    "session_id",
    "created_at",
    "ip_address",
    "user_agent",
    "properties",
}

ALLOWED_EVENT_TYPES = {"page_view", "purchase", "error"}


def _make_event() -> dict:
    return generate_event(
        user_id=1,
        session_id="sess-abc",
        when=datetime.now(timezone.utc),
    )


def _make_event_of_type(target_type: str, max_attempts: int = 1000) -> dict:
    """가중치 분포 때문에 특정 타입이 한 번에 안 뽑힐 수 있어,
    max_attempts 회 안에 목표 타입을 만나면 그 이벤트를 반환한다.
    """
    for _ in range(max_attempts):
        event = _make_event()
        if event["event_type"] == target_type:
            return event
    pytest.fail(f"{target_type} 타입을 {max_attempts}회 안에 생성하지 못했습니다.")


# ============================================================
# 공통 필드 검증
# ============================================================
def test_generate_event_contains_all_required_fields():
    event = _make_event()
    assert set(event.keys()) == REQUIRED_FIELDS


def test_event_type_is_in_allowed_set():
    event = _make_event()
    assert event["event_type"] in ALLOWED_EVENT_TYPES


# ============================================================
# 타입별 properties 키 검증
# ============================================================
def test_purchase_properties_has_amount_and_product_id():
    props = _make_event_of_type("purchase")["properties"]
    assert "amount" in props
    assert "product_id" in props
    assert isinstance(props["amount"], int)


def test_error_properties_has_error_code():
    assert "error_code" in _make_event_of_type("error")["properties"]


def test_page_view_properties_has_path():
    assert "path" in _make_event_of_type("page_view")["properties"]


# ============================================================
# 분포 검증 (확률적)
# ============================================================
def test_event_type_distribution_roughly_matches_weights():
    """80 / 15 / 5 가중치가 실제 분포에 근사하는지 확인.

    10,000건 샘플링 시 오차 ±5%p 허용.
    """
    n = 10_000
    counter = Counter(pick_event_type() for _ in range(n))

    expected = {"page_view": 0.80, "purchase": 0.15, "error": 0.05}
    tolerance = 0.05

    for event_type, expected_ratio in expected.items():
        actual_ratio = counter[event_type] / n
        assert abs(actual_ratio - expected_ratio) < tolerance, (
            f"{event_type} 비율 {actual_ratio:.3f} 가 기대치 {expected_ratio} 와"
            f" {tolerance} 이상 차이남"
        )
