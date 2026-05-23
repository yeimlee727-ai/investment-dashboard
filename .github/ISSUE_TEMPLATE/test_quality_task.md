---
name: Test / quality task
about: 테스트, CI, 포맷, 문서 품질 개선 작업을 정의합니다.
title: "[Quality] "
labels: quality
assignees: ""
---

## 개선 대상


## 현재 문제


## 추가할 테스트


## 검증 명령

```bash
cd investment_dashboard
python -m compileall .
python -m pytest -vv
ruff check .
black --check .
```

## 기대 효과


## 관련 파일


## 완료 기준

- [ ] pytest를 추가 또는 보완합니다.
- [ ] 외부 API에 의존하지 않는 테스트입니다.
- [ ] SAMPLE 데이터 또는 mock 데이터만 사용합니다.
- [ ] ruff check . 통과
- [ ] black --check . 통과

