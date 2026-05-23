## 변경 요약


## 변경 유형

- [ ] 기능 추가
- [ ] 버그 수정
- [ ] 테스트 보강
- [ ] 문서 수정
- [ ] 리팩토링
- [ ] CI/품질 개선

## 관련 Issue


## 관련 labels


## 관련 Agent 역할

- [ ] Data Provider
- [ ] DART / Scoring
- [ ] Backtest
- [ ] UI
- [ ] Tests / CI / Docs

## 변경 파일 목록


## 공통 파일 수정 여부

- [ ] 공통 파일을 수정하지 않았습니다.
- [ ] 공통 파일을 수정했으며 `AGENTS.md`의 공유 파일 수정 규칙을 확인했습니다.

## 테스트 결과

```bash
cd investment_dashboard
python -m compileall .
python -m pytest -vv
ruff check .
black --check .
```

## 스크린샷 또는 실행 화면


## 영향 범위


## 롤백 방법


## 남은 제한사항


## branch protection 확인

- [ ] main 브랜치는 direct push 대신 PR 기반 merge를 사용합니다.
- [ ] required status checks가 설정되어 있거나, 설정 필요 여부를 확인했습니다.
- [ ] CI required checks 통과 전 merge하지 않습니다.

## 안전성 체크

- [ ] 실제 주문 기능을 추가하지 않았습니다.
- [ ] 실제 증권사 주문 API를 호출하지 않습니다.
- [ ] 실제 계좌 조회 기능을 추가하지 않았습니다.
- [ ] TossBrokerPlaceholder를 실제 구현체로 변경하지 않았습니다.
- [ ] MockBroker는 가상 주문만 처리합니다.
- [ ] API Key, 토큰, 계좌정보, 실거래 데이터를 커밋하지 않았습니다.

## 품질 검증 체크

- [ ] cd investment_dashboard
- [ ] python -m compileall .
- [ ] python -m pytest -vv
- [ ] ruff check .
- [ ] black --check .
- [ ] GitHub Actions CI 통과

## 데이터 모드 체크

- [ ] SAMPLE 모드에서 정상 동작합니다.
- [ ] REAL_WITH_FALLBACK 모드에서 실패 시 샘플 fallback이 동작합니다.
- [ ] SAMPLE / FALLBACK / REAL DATA 표시가 명확합니다.
