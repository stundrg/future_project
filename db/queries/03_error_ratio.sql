-- ============================================================
-- 에러율 (서비스 안정성 KPI)
--   목적: 전체 이벤트 대비 error 비율을 단일 숫자로
--   기대: 약 5% 근처 (생성기 가중치 기준)
-- ============================================================
WITH stats AS (
    SELECT
        COUNT(*) FILTER (WHERE event_type = 'error') AS error_count,
        COUNT(*)                                     AS total_count
    FROM events
)
SELECT
    error_count,
    total_count,
    ROUND(100.0 * error_count / NULLIF(total_count, 0), 2) AS error_rate_percentage
FROM stats;
