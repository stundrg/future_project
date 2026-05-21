-- ============================================================
-- 시간대별 이벤트 추이 (최근 7일, 시간 단위)
--   목적: 시계열 패턴 파악 (Grafana time series 패널 데이터)
--   기대: 시간대별 / 이벤트 타입별 발생량 추이
-- ============================================================
SELECT
    date_trunc('hour', created_at)  AS hour,
    event_type,
    COUNT(*)                        AS event_count
FROM events
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY hour, event_type
ORDER BY hour DESC, event_type;
