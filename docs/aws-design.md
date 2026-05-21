# AWS 아키텍처 설계 (선택 과제 B)

> 본 문서는 현재 docker-compose 기반 미니 파이프라인을 **AWS 운영 환경**으로 옮긴다고 가정했을 때의 설계안.

---

## 1. 개요

### 현재 구조의 한계
- 단일 머신에서 모든 컴포넌트 실행 → SPOF
- 생성기와 DB 가 직접 결합 → DB 장애가 생성기로 즉시 전파
- 모니터링/알림 부재
- 데이터 백업 책임이 사용자에게

### AWS 운영 시 핵심 변경점
- 생성기-DB 사이에 **메시지 큐(Kinesis)** 도입 → 디커플링 / 버퍼링 / 재처리
- **Managed 서비스** 우선 사용 → 운영 부담 최소화
- 모니터링/알림 자동화 (CloudWatch + SNS)

---

## 2. 아키텍처 다이어그램

```mermaid
flowchart LR
    subgraph Producer["Producer Layer"]
        G["Generator<br/>(ECS Fargate)"]
    end

    subgraph Ingest["Ingest Layer"]
        K["Kinesis Data Streams"]
    end

    subgraph Consumer["Consumer Layer"]
        L["Kinesis Firehose<br/>(또는 Lambda)"]
    end

    subgraph Storage["Storage Layer"]
        R[("RDS PostgreSQL<br/>Multi-AZ")]
        S[("S3<br/>Cold Archive")]
    end

    subgraph Viz["Visualization"]
        M["Amazon Managed<br/>Grafana"]
    end

    subgraph Ops["Observability"]
        CW["CloudWatch<br/>Logs + Metrics"]
        SNS["SNS Alarm"]
    end

    G -->|put_records| K
    K --> L
    L -->|hot data| R
    L -.->|archive| S
    R --> M

    G -.-> CW
    L -.-> CW
    R -.-> CW
    CW -.->|threshold| SNS
```

---

## 3. 데이터 플로우

1. **Generator (ECS Fargate task)**: 매초 2~5건 이벤트 생성, Kinesis 에 `put_records` 호출
2. **Kinesis Data Streams**: 이벤트 버퍼 (보존 24시간~7일), shard 단위 처리량 보장
3. **Kinesis Firehose**: shard 에서 데이터 읽어 RDS 로 배치 적재
4. **RDS PostgreSQL**: hot data 저장 (현재 `events` 테이블 스키마 그대로)
5. **S3 Cold Archive**: Firehose 가 동시에 S3 로 dump → 장기 보관 + Athena 분석 가능
6. **Managed Grafana**: RDS 를 데이터소스로 → 현재 4 패널 대시보드 그대로 사용

---

## 4. AWS 서비스 매핑

| 현재 컴포넌트 | AWS 서비스 | 역할 |
|---------------|-----------|------|
| `generator` 컨테이너 | **ECS Fargate** | 서버리스 컨테이너 실행 |
| (없음) | **Kinesis Data Streams** | 디커플링 + 버퍼링 |
| `db.py` 적재 로직 | **Kinesis Firehose** | 자동 배치 적재 |
| `postgres` 컨테이너 | **RDS PostgreSQL (Multi-AZ)** | Managed DB |
| (없음) | **S3** | 장기 보관 + Athena 분석 |
| `grafana` 컨테이너 | **Amazon Managed Grafana** | Managed 시각화 |
| (없음) | **CloudWatch + SNS** | 모니터링 + 알림 |
| `.env` | **AWS Secrets Manager** | 자격증명 관리 |

---

## 5. 서비스 선택 이유 & 대안

### Generator → ECS Fargate
- **선택 이유**: 현재 컨테이너 그대로 실행 가능. 서버리스라 인프라 관리 불필요
- **대안**:
  - EC2 — 인프라 직접 관리 부담
  - Lambda — 15분 실행 한도, 지속 실행 부적합
  - ECS on EC2 — 클러스터 운영 필요

### 디커플링 → Kinesis Data Streams
- **선택 이유**: AWS 네이티브, IAM/CloudWatch 통합 단순, shard 단위 처리량 보장(1MB/s · 1000건/s per shard), 24시간~7일 보존으로 재처리 가능
- **대안**:
  - SQS — 순서 보장 약함, 멀티 컨슈머 어려움
  - MSK (Kafka) — 강력하지만 운영 복잡 + 비용↑. 본 규모엔 오버
  - 큐 없이 직접 RDS 적재 — 디커플링 X, DB 장애 직격타

### 적재 → Kinesis Firehose
- **선택 이유**: 코드 없이 Kinesis → RDS / S3 자동 배치. 운영 부담 최소
- **대안**:
  - Lambda 컨슈머 — 더 유연하나 코드/운영 부담
  - EC2 컨슈머 — 풀 운영 필요

### 저장 → RDS PostgreSQL (Multi-AZ)
- **선택 이유**: 현재 스키마/쿼리 그대로 사용 → 마이그레이션 비용 0. Multi-AZ failover + 자동 백업
- **대안**:
  - Aurora PostgreSQL — 더 빠르나 비용↑. 본 규모엔 RDS 로 충분
  - DynamoDB — NoSQL, 시계열 분석 약함
  - Timestream — 시계열 전용. SQL 표현력은 RDS 보다 약함

### 시각화 → Amazon Managed Grafana
- **선택 이유**: 현재 대시보드 JSON 그대로 import 가능. 운영 부담 0. IAM 인증 통합
- **대안**:
  - QuickSight — AWS 네이티브이지만 UX 다름, 마이그레이션 비용
  - self-hosted Grafana on ECS — 운영 부담↑

---

## 6. 확장성 / 비용 / 운영

### 확장성
- **수평 확장**: ECS Fargate task 수 조정으로 generator 스케일
- **Kinesis on-demand**: 트래픽에 따라 shard 자동 스케일
- **RDS Read Replica**: 분석 쿼리는 replica 로 분리 (write/read 분리)

### 비용 추정 (소규모 운영 기준)

| 서비스 | 월 비용 |
|--------|---------|
| ECS Fargate (1 task) | ~$30 |
| Kinesis Data Streams (1 shard) | ~$11 + 데이터 비용 |
| Kinesis Firehose | GB 처리량당 과금 |
| RDS db.t3.small Multi-AZ | ~$60 |
| Amazon Managed Grafana | $9/active user |
| **합계** | **~$120/월** (변동성 있음) |

### 운영
- **모니터링**: CloudWatch 가 ECS/Kinesis/RDS 메트릭 자동 수집
- **알림**: CloudWatch Alarm → SNS → Slack/이메일 (예: 에러율 5% 초과 시)
- **보안**:
  - IAM 역할 최소 권한 원칙
  - RDS 는 private subnet, Kinesis VPC endpoint 사용
  - Secrets Manager 로 DB 자격증명 관리 (`.env` 대체)

---

## 7. 향후 개선

- **데이터 lake 통합**: S3 데이터를 Athena/Glue 로 분석 → 비용 효율적 ad-hoc 쿼리
- **IaC**: CDK / Terraform 으로 인프라 코드화 → 환경 복제 자동화
- **Step Functions**: 복잡한 ETL workflow 도입
- **EventBridge + Lambda**: 특정 이벤트 패턴 감지 시 즉시 처리 (예: 에러 폭주 알림 자동화)
