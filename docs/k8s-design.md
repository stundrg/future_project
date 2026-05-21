# Kubernetes 설계 (선택 과제 A — 매핑 설계)

> 본 문서는 현재 docker-compose 기반 파이프라인을 **Kubernetes 환경에서 운영**한다고 가정했을 때의 매니페스트 매핑 + 트레이드오프 정리.
>
> 본 과제의 선택 과제 충족은 AWS 설계(`docs/aws-design.md`)로 완료했으며, K8s 는 **두 번째 관점 사고를 정리** 차원에서 추가. 실제 yaml 매니페스트는 작성하지 않고 설계만 정리한다 (어설픈 yaml 보다 설계 사고의 정확성을 우선).

---

## 1. 개요

### docker-compose 의 한계 (K8s 도입 동기)
- 단일 머신/단일 노드 → 수평 확장 불가
- 셀프힐링/롤링 업데이트 없음 (헬스체크는 있으나 자동 복구 제한)
- 리소스 격리/쿼터 없음
- 컨테이너 간 서비스 디스커버리 = docker 네트워크 (멀티 노드 X)

### K8s 도입 시 변경점
- **Deployment / StatefulSet**: 셀프힐링 + 롤링 업데이트
- **Service**: 클러스터 내부 디스커버리 + 외부 노출
- **ConfigMap / Secret**: 환경변수와 자격증명 분리
- **PVC**: 영속 스토리지 추상화
- **HPA**: 트래픽 기반 자동 스케일링

---

## 2. 매니페스트 매핑

| 현재 (docker-compose) | K8s 리소스 | 이유 |
|----------------------|-----------|------|
| `generator` 컨테이너 | **Deployment** | stateless 워크로드, 셀프힐링/스케일 |
| `postgres` 컨테이너 + named volume | **StatefulSet + PVC** | 안정적 네트워크 ID + 영속 스토리지 |
| `grafana` 컨테이너 + named volume | **Deployment + PVC** | provisioning 으로 매번 재구성 가능 |
| 환경변수 (POSTGRES_*, BATCH_SIZE 등) | **ConfigMap** | 일반 설정 분리 |
| 비밀번호 (POSTGRES_PASSWORD, GF_*_PASSWORD) | **Secret** | 자격증명 보호 |
| 컨테이너 간 통신 | **Service (ClusterIP)** | 내부 디스커버리 |
| Grafana 외부 노출 | **Service (LoadBalancer 또는 NodePort) + Ingress** | 외부 접근 |
| `docker-entrypoint-initdb.d` 마운트 | **ConfigMap mount + initContainer** | 초기 스키마 적용 |
| Grafana provisioning 마운트 | **ConfigMap mount** | 데이터소스 + 대시보드 |

---

## 3. 리소스별 선택 이유 + 대안

### Generator → Deployment
- **선택 이유**: stateless (이벤트 생성만, 상태 보존 불필요). 셀프힐링 + 무중단 재시작 자연스러움
- **대안**:
  - **DaemonSet** — 노드마다 1개. generator 는 모든 노드에 띄울 필요 없음
  - **StatefulSet** — 안정적 ID 필요할 때. generator 는 ID 무관
  - **Job/CronJob** — 1회 실행/주기적. 본 generator 는 지속 실행

### PostgreSQL → StatefulSet + PVC
- **선택 이유**:
  - 안정적 네트워크 ID 보장 (`postgres-0` 같은 hostname 유지)
  - 각 인스턴스마다 고유 PVC → 데이터 보존
- **대안**:
  - **Deployment + PVC** — single instance 라면 가능하나 pod 재생성 시 hostname 변경 위험
  - **외부 RDS** — 운영에서는 K8s 안에 DB 안 두는 것이 정석. 본 설계는 학습/단일 클러스터 가정

### Grafana → Deployment + PVC
- **선택 이유**: provisioning 으로 매 기동 시 데이터소스/대시보드 재구성됨 → stateful 성질 약함
- **PVC 는 보존용**: 사용자가 GUI 에서 만든 ad-hoc 대시보드 보존 정도
- **대안**:
  - **StatefulSet** — 더 안전하지만 grafana 는 사실상 stateless 에 가까워 과한 선택

### Secret vs ConfigMap 분리 기준
| 종류 | 대상 |
|------|------|
| **ConfigMap** | `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_HOST`, `BATCH_SIZE`, `SEED_COUNT`, `STREAM_MIN_RPS` 등 |
| **Secret** | `POSTGRES_PASSWORD`, `GF_SECURITY_ADMIN_PASSWORD` |

- Secret 은 etcd 에 base64 인코딩 저장 + RBAC 접근 제어 가능 (평문 노출 방지)

### Service 종류
| 서비스 | 타입 | 이유 |
|--------|------|------|
| postgres | **ClusterIP** | 외부 노출 불필요 (generator/grafana 만 접근) |
| generator | (서비스 X) | 외부로 노출할 인터페이스 없음 (push-based) |
| grafana | **LoadBalancer** 또는 **NodePort + Ingress** | 평가자/사용자 외부 접속 필요 |

### Postgres 초기 스키마 적용
- **방법 1: ConfigMap mount** — `db/init/01_schema.sql` 을 ConfigMap 으로 만들고 `/docker-entrypoint-initdb.d/` 에 mount. 단순
- **방법 2: initContainer** — busybox/psql 컨테이너로 직접 적용. 더 유연하지만 복잡
- **권장**: ConfigMap mount (현재 docker-compose 방식과 동일 사고)

---

## 4. 운영 고려

### Health check
- **postgres**: `livenessProbe` = `pg_isready -U $POSTGRES_USER`, `readinessProbe` 동일
- **grafana**: `livenessProbe` = `GET /api/health`, `readinessProbe` 동일
- **generator**: 자체 HTTP endpoint 없음 → `tcp socket probe` 또는 추가 health endpoint 도입 필요

### Resource limits / requests (참고치)
| 컴포넌트 | requests | limits |
|----------|----------|--------|
| generator | 100m CPU / 128Mi RAM | 200m / 256Mi |
| postgres | 500m CPU / 1Gi RAM | 1000m / 2Gi |
| grafana | 200m CPU / 256Mi RAM | 500m / 512Mi |

### 자동 스케일링 (HPA)
- **generator**: CPU 70% 기준 1~5 replica (트래픽 기반)
- **postgres**: HPA 적용 X (stateful, 수직 확장 또는 read replica 분리)
- **grafana**: 옵션 (요청 트래픽 적으면 불필요)

### 보안
- **NetworkPolicy**: postgres 는 generator/grafana 에서만 접근 허용
- **RBAC**: ServiceAccount 별 최소 권한
- **Pod Security Standard**: `restricted` profile 적용

---

## 5. 향후 개선

- **Helm chart**: 매니페스트 패키징 + `values.yaml` 환경별 분기
- **Kustomize**: dev/staging/prod overlay 분리
- **Ingress + cert-manager**: HTTPS + Let's Encrypt 자동 발급
- **HorizontalPodAutoscaler**: 트래픽 기반 generator 자동 스케일
- **External Secrets Operator**: AWS Secrets Manager / Vault 와 연동
- **GitOps (ArgoCD / Flux)**: git push → 자동 동기화 배포
- **외부 DB 전환**: 운영 시 RDS 같은 managed DB 로 이동 (StatefulSet 운영 부담 회피)
