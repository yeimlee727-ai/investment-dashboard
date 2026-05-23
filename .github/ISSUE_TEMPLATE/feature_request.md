---
name: Feature request
about: 기능 개발 작업을 안전하게 정의합니다.
title: "[Feature] "
labels: enhancement
assignees: ""
---

## 기능명


## 작업 목적


## 수정 대상 영역


## 관련 Agent 역할

- [ ] Data Provider
- [ ] DART / Scoring
- [ ] Backtest
- [ ] UI
- [ ] Tests / CI / Docs

## 수정 가능 파일/폴더


## 수정 금지 파일/폴더


## 실제 주문 기능 관련 영향 여부

- [ ] 실제 주문 기능을 추가하지 않습니다.
- [ ] 실제 증권사 주문 API를 호출하지 않습니다.
- [ ] 실제 계좌 조회 기능을 추가하지 않습니다.
- [ ] TossBrokerPlaceholder를 실제 구현체로 변경하지 않습니다.
- [ ] MockBroker는 가상 주문만 처리합니다.
- [ ] API Key, 토큰, 계좌정보를 커밋하지 않습니다.
- [ ] 변경 후 CI 검증 명령을 통과시킵니다.

## 테스트 요구사항

```bash
cd investment_dashboard
python -m compileall .
python -m pytest -vv
ruff check .
black --check .
```

## 완료 기준


## 참고 사항

