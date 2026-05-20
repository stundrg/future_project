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
