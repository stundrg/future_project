# Event Log Pipeline

> 웹 서비스의 이벤트 로그를 생성하고, 저장하고, 분석하고, 시각화하는
> 미니 데이터 파이프라인.

`docker compose up` 한 번으로 이벤트 생성기, PostgreSQL, Grafana가 함께 실행된다.

---

## 기술 스택

- **Python** — 이벤트 생성기
- **PostgreSQL** — 이벤트 저장
- **Grafana** — 분석 결과 시각화
- **Docker Compose** — 전체 스택 오케스트레이션

---

## 이벤트 스키마

모든 이벤트는 단일 `events` 테이블에 저장한다. 공통 필드는 컬럼으로 분리하고, 이벤트 타입에 따라 달라지는 가변 필드만 `properties` 컬럼(JSONB)에 담는다.

### 테이블 구조

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `event_id` | `UUID` | 이벤트 고유 식별자 |
| `event_type` | `VARCHAR(32)` | `page_view` / `purchase` / `error` |
| `user_id` | `INT` | 이벤트를 발생시킨 사용자 |
| `session_id` | `VARCHAR(64)` | 사용자 세션 식별자 |
| `created_at` | `TIMESTAMPTZ` | 이벤트 발생 시각 (UTC) |
| `ip_address` | `INET` | 클라이언트 IP |
| `user_agent` | `TEXT` | 브라우저/디바이스 정보 |
| `properties` | `JSONB` | 이벤트 타입별 가변 필드 |

### 이벤트 타입별 `properties` 예시

| 타입 | `properties` |
|------|--------------|
| `page_view` | `{"path": "/products/42", "referrer": "/home"}` |
| `purchase`  | `{"product_id": "P-001", "amount": 29900, "currency": "KRW"}` |
| `error`     | `{"error_code": "500", "message": "...", "stack_trace": "..."}` |

### 설계 이유

JSON을 통째로 저장하면 분석마다 JSONB 파싱이 필요하고, 이벤트 타입별로 테이블을 분리하면 통합 분석마다 UNION이 필요하다. 공통 컬럼은 분리하여 인덱스로 빠르게 집계하고, 타입별로 다른 부분만 JSONB로 두는 절충안을 선택했다.
