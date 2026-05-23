# GitHub Labels Guide

이 문서는 멀티 에이전트 병렬 개발에서 Issue와 PR을 일관되게 분류하기 위한 label 운영 기준입니다.

## 기능 영역 Labels

| Label | 의미 | 사용 예시 |
| --- | --- | --- |
| `area:data-provider` | 가격 데이터 provider, 샘플 fallback, yfinance 조회 영역 | `MarketDataProvider` fallback 개선 |
| `area:dart` | DART API, 공시 수집, 공시 분류 영역 | DART API 오류 처리 수정 |
| `area:scoring` | 종목 점수화, 이벤트/리스크 점수 영역 | 위험 공시 risk penalty 보정 |
| `area:backtest` | 백테스트 엔진, 전략, 수수료/슬리피지 영역 | 손절/익절 판정 테스트 추가 |
| `area:ui` | Streamlit 앱, 페이지, 표시 문구 영역 | SAMPLE MODE 배지 개선 |
| `area:broker` | broker interface, MockBroker, Toss placeholder 영역 | MockBroker 가상 주문 로그 개선 |
| `area:risk` | RiskEngine, 주문 한도, 일 손실 제한 영역 | 일 손익 계산 테스트 보강 |
| `area:tests` | pytest, fixture, smoke test 영역 | 외부 API 없는 provider 테스트 추가 |
| `area:ci` | GitHub Actions, lint, format, quality gate 영역 | CI Python 버전 조정 |
| `area:docs` | README, AGENTS, 운영 문서 영역 | branch protection 문서 추가 |

## 작업 유형 Labels

| Label | 의미 | 사용 예시 |
| --- | --- | --- |
| `type:feature` | 새로운 기능 또는 기존 기능 확장 | 데이터 모드 선택 UI 추가 |
| `type:bug` | 재현 가능한 오류 수정 | 빈 DataFrame에서 화면 오류 수정 |
| `type:test` | 테스트 추가 또는 보완 | BacktestEngine 회귀 테스트 추가 |
| `type:refactor` | 동작 변경 없는 구조 개선 | provider 인터페이스 정리 |
| `type:docs` | 문서 추가 또는 수정 | README 제한사항 보완 |
| `type:ci` | CI workflow 또는 자동 검증 개선 | required check 명령 조정 |
| `type:security` | 민감정보, API key, 안전성 관련 개선 | secrets 커밋 방지 안내 추가 |
| `type:quality` | lint, format, 유지보수성 개선 | ruff 경고 정리 |

## 우선순위 Labels

| Label | 의미 | 사용 예시 |
| --- | --- | --- |
| `priority:p0` | 즉시 수정해야 하는 실행 불가, 보안, 실제 주문 위험 | 앱 전체 실행 실패, secret 노출 |
| `priority:p1` | 주요 기능 장애 또는 CI 실패 | pytest 실패, 주요 페이지 오류 |
| `priority:p2` | 일반 기능 개선 또는 제한된 버그 | 특정 데이터 모드 표시 오류 |
| `priority:p3` | 낮은 우선순위 개선, 문서, 정리 | 문구 개선, 설명 보완 |

## 상태 Labels

| Label | 의미 | 사용 예시 |
| --- | --- | --- |
| `status:needs-triage` | 아직 범위, 담당, 우선순위가 확정되지 않음 | 새 Issue 기본 상태 |
| `status:ready` | 작업 범위와 담당 Agent가 확정됨 | 구현 착수 가능 |
| `status:in-progress` | 작업 진행 중 | 브랜치에서 개발 진행 |
| `status:blocked` | 외부 결정, 충돌, 권한, 정보 부족으로 대기 | API 정책 확인 필요 |
| `status:needs-review` | PR 리뷰 또는 검증이 필요함 | CI 통과 후 리뷰 대기 |

## 안전성 Labels

| Label | 의미 | 사용 예시 |
| --- | --- | --- |
| `safety:no-real-order` | 실제 주문 기능이 없어야 하는 일반 안전 작업 | 대부분의 기능/문서/테스트 작업 |
| `safety:broker-change` | broker 계층과 관련되어 추가 확인이 필요한 작업 | MockBroker 가상 주문 로직 변경 |
| `safety:data-only` | 조회용 데이터 처리에 한정된 작업 | yfinance fallback 개선 |
| `safety:mock-only` | 모의매매 또는 mock 데이터에만 영향을 주는 작업 | 가상 주문 표시 개선 |

## 운영 권장사항

- 새 Issue에는 최소 하나의 `area:*`, 하나의 `type:*`, 하나의 `status:*` label을 붙입니다.
- 실제 주문 기능과 오해될 수 있는 변경은 `safety:*` label을 반드시 붙입니다.
- `area:broker` 또는 `safety:broker-change` 작업은 `AGENTS.md`의 금지 사항을 먼저 확인합니다.
- CI 실패는 `priority:p1`, `area:ci`, `type:bug` 또는 `type:ci`를 함께 사용합니다.
- 문서만 바꾸는 작업은 보통 `area:docs`, `type:docs`, `priority:p3`를 사용합니다.
