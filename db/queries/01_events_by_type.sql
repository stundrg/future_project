-- ============================================================
-- 이벤트 타입별 발생 횟수 + 비율
--   목적: 데이터가 의도한 분포(80/15/5)로 들어왔는지 검증
--   기대: page_view ~80%, purchase ~15%, error ~5%
-- ============================================================
SELECT
    event_type,
    COUNT(*)                                                AS event_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)      AS percentage
FROM events
GROUP BY event_type
ORDER BY event_count DESC;
