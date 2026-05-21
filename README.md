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

## 실행 방법

### 사전 요구사항
- Docker 20+
- Docker Compose v2

### 실행

```bash
cp .env.example .env       # 환경변수 파일 준비 (필요 시 값 수정)
docker compose up -d       # 백그라운드 실행
```

`postgres` healthcheck 통과 후 `generator` 가 자동으로 시작된다.

### 상태 확인

```bash
docker compose ps                       # 컨테이너 상태
docker compose logs -f generator        # 생성기 실시간 로그
```

### 적재 데이터 확인

```bash
docker compose exec postgres psql -U eventuser -d eventdb \
  -c "SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY event_type;"
```

### 정리

```bash
docker compose down -v   # 볼륨까지 삭제 (다음 기동 시 스키마 다시 적용됨)
```

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

---

## 분석 쿼리

분포 · 추이 · 품질 · 사용자 4가지 관점을 한 번에 보기 위해 다음 4개 쿼리를 정의했다.
전체 SQL은 `db/queries/` 에 있고, 다음 단계의 Grafana 대시보드 4개 패널과 1:1 매핑된다.

### 실행 방법

```bash
# 단일 쿼리
docker compose exec -T postgres psql -U eventuser -d eventdb \
  < db/queries/01_events_by_type.sql

# 전체 일괄 실행
for f in db/queries/*.sql; do
  echo "==================== $f ===================="
  docker compose exec -T postgres psql -U eventuser -d eventdb < "$f"
done
```

---

### 1. 이벤트 타입별 발생 횟수 + 비율

데이터 분포가 의도한 비율(80/15/5)로 들어왔는지 확인.

```sql
-- db/queries/01_events_by_type.sql
SELECT
    event_type,
    COUNT(*)                                                AS event_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)      AS percentage
FROM events
GROUP BY event_type
ORDER BY event_count DESC;
```

```
 event_type | event_count | percentage
------------+-------------+------------
 page_view  |       13678 |      80.53
 purchase   |        2492 |      14.67
 error      |         816 |       4.80
```

→ 의도한 80/15/5 분포에 잘 부합한다.

---

### 2. 시간대별 이벤트 추이 (최근 7일, 시간 단위)

시계열 패턴 파악 — Grafana time series 패널의 입력 쿼리로 사용 예정.

```sql
-- db/queries/02_hourly_trend.sql
SELECT
    date_trunc('hour', created_at)  AS hour,
    event_type,
    COUNT(*)                        AS event_count
FROM events
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY hour, event_type
ORDER BY hour DESC, event_type;
```

결과 (최근 10행 발췌):

```
          hour          | event_type | event_count
------------------------+------------+-------------
 2026-05-21 03:00:00+00 | error      |         169
 2026-05-21 03:00:00+00 | page_view  |        2601
 2026-05-21 03:00:00+00 | purchase   |         496
 2026-05-20 19:00:00+00 | page_view  |          10
 2026-05-20 19:00:00+00 | purchase   |           3
 2026-05-20 18:00:00+00 | error      |         142
 2026-05-20 18:00:00+00 | page_view  |        2245
 2026-05-20 18:00:00+00 | purchase   |         420
 2026-05-20 15:00:00+00 | error      |          42
 2026-05-20 15:00:00+00 | page_view  |         667
```

---

### 3. 에러율 (서비스 안정성 KPI)

전체 이벤트 대비 error 비율 — 단일 숫자(KPI 카드용).

```sql
-- db/queries/03_error_ratio.sql
SELECT
    COUNT(*) FILTER (WHERE event_type = 'error')   AS error_count,
    COUNT(*)                                       AS total_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE event_type = 'error')
             / NULLIF(COUNT(*), 0),
        2
    ) AS error_rate_percentage
FROM events;
```

```
 error_count | total_count | error_rate_percentage
-------------+-------------+-----------------------
         800 |       16593 |                  4.82
```

→ 의도한 5% 가중치에 근사 (이벤트 생성기 동작 검증).

---

### 4. 상위 활성 유저 Top 10

단순 이벤트 수만 보면 패턴 구분이 어렵기에 **세션 수 / 최근성**까지 함께 본다.

```sql
-- db/queries/04_top_active_users.sql
SELECT
    user_id,
    COUNT(*)                       AS event_count,
    COUNT(DISTINCT session_id)     AS session_count,
    MAX(created_at)                AS last_seen_at
FROM events
GROUP BY user_id
ORDER BY event_count DESC
LIMIT 10;
```

```
 user_id | event_count | session_count |         last_seen_at
---------+-------------+---------------+-------------------------------
      69 |         194 |           194 | 2026-05-21 03:55:50.381037+00
      49 |         192 |           192 | 2026-05-21 03:55:24.199099+00
      27 |         189 |           189 | 2026-05-21 03:55:28.23242+00
      58 |         188 |           188 | 2026-05-21 03:55:25.207868+00
      72 |         186 |           186 | 2026-05-21 03:55:44.347619+00
      91 |         185 |           185 | 2026-05-21 03:55:16.137428+00
      10 |         184 |           184 | 2026-05-21 03:55:21.174338+00
      17 |         183 |           183 | 2026-05-21 03:55:43.339946+00
       5 |         183 |           183 | 2026-05-21 03:55:18.153335+00
      21 |         182 |           182 | 2026-05-21 03:55:44.347152+00
```

→ `event_count == session_count` 인 것은 현재 생성기가 매 이벤트마다 새 `session_id` 를 발급하기 때문(단순성 우선). 세션 유지 모델은 향후 개선 항목.
