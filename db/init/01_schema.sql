-- ============================================================
-- 이벤트 로그 파이프라인 - 스키마 정의
--
-- 모든 이벤트는 단일 events 테이블에 저장한다.
-- 공통 필드는 컬럼으로 분리하고, 이벤트 타입별 가변 필드만
-- properties(JSONB) 컬럼에 담는다.
-- ============================================================

-- ============================================================
-- events 테이블
-- ============================================================
CREATE TABLE events (
    event_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type    VARCHAR(32)  NOT NULL,
    user_id       INT          NOT NULL,
    session_id    VARCHAR(64)  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ip_address    INET,
    user_agent    TEXT,
    properties    JSONB        NOT NULL DEFAULT '{}'::jsonb,

    -- 이벤트 타입은 정의된 값만 허용 (무결성 보장)
    CONSTRAINT events_event_type_check
        CHECK (event_type IN ('page_view', 'purchase', 'error'))
);

-- ============================================================
-- 인덱스
--  - event_type : 타입별 집계 (GROUP BY event_type)
--  - created_at : 시간대별 추이 (DATE_TRUNC + WHERE)
--  - user_id    : 유저별 활동 분석 (WHERE user_id = ?)
-- ============================================================
CREATE INDEX idx_events_event_type ON events (event_type);
CREATE INDEX idx_events_created_at ON events (created_at DESC);
CREATE INDEX idx_events_user_id    ON events (user_id);

-- ============================================================
-- 코멘트 (스키마 자기설명)
-- ============================================================
COMMENT ON TABLE  events             IS '웹 서비스 이벤트 로그 (모든 이벤트 타입 단일 테이블)';
COMMENT ON COLUMN events.event_id    IS '이벤트 고유 식별자 (UUID v4)';
COMMENT ON COLUMN events.event_type  IS '이벤트 타입 (page_view, purchase, error)';
COMMENT ON COLUMN events.user_id     IS '이벤트를 발생시킨 사용자 ID';
COMMENT ON COLUMN events.session_id  IS '사용자 세션 식별자 (방문 단위)';
COMMENT ON COLUMN events.created_at  IS '이벤트 발생 시각 (UTC, TIMESTAMPTZ)';
COMMENT ON COLUMN events.ip_address  IS '클라이언트 IP 주소 (INET)';
COMMENT ON COLUMN events.user_agent  IS '클라이언트 브라우저/디바이스 정보';
COMMENT ON COLUMN events.properties  IS '이벤트 타입별 가변 필드 (JSONB)';
