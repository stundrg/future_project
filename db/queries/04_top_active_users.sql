-- ============================================================
-- 상위 활성 유저 Top 10
--   목적: 가장 활발한 사용자 식별 (유저 단위 분석)
--   기대: 유저 100명 중 상위 10명의 이벤트 / 세션 / 최근성
-- ============================================================
SELECT
    user_id,
    COUNT(*)                       AS event_count,
    COUNT(DISTINCT session_id)     AS session_count,
    MAX(created_at)                AS last_seen_at
FROM events
GROUP BY user_id
ORDER BY event_count DESC
LIMIT 10;
