# Branch Protection Guide

이 문서는 GitHub 웹 UI에서 `main` 브랜치 보호 규칙을 수동으로 설정하는 방법을 설명합니다.

> 주의: 이 저장소는 문서로만 권장 설정을 안내합니다. 자동 스크립트나 코드로 branch protection을 강제 적용하지 않습니다.

## 설정 경로

1. GitHub 저장소로 이동합니다.
2. `Settings`를 엽니다.
3. 왼쪽 메뉴에서 `Branches`를 선택합니다.
4. `Branch protection rules`에서 `Add branch protection rule`을 선택합니다.
5. `Branch name pattern`에 `main`을 입력합니다.

## 권장 설정

| 설정 | 권장값 | 설명 |
| --- | --- | --- |
| Restrict direct push to `main` | Enable | `main` 브랜치에 직접 push하지 않고 PR 기반으로 변경합니다. |
| Require a pull request before merging | Enable | 모든 변경은 PR 리뷰와 검증을 거치게 합니다. |
| Require status checks to pass before merging | Enable | CI가 실패한 PR은 merge하지 않습니다. |
| Required status checks | `CI` | GitHub Actions workflow가 통과해야 merge할 수 있게 합니다. |
| Require branches to be up to date before merging | Recommended | 최신 `main` 기준으로 CI를 다시 확인합니다. |
| Require conversation resolution before merging | Recommended | 리뷰 코멘트가 해결된 뒤 merge합니다. |
| Allow force pushes | Disable | 히스토리 손상을 방지합니다. |
| Allow deletions | Disable | 보호 브랜치 삭제를 방지합니다. |
| Include administrators | Optional | 관리자에게도 같은 규칙을 적용할지 팀 운영 방식에 따라 선택합니다. |

## Required Status Checks

이 저장소의 CI workflow는 다음 명령을 실행합니다.

```bash
cd investment_dashboard
python -m compileall .
python -m pytest -vv
ruff check .
black --check .
```

GitHub UI에서 required status check 이름은 보통 `CI` 또는 workflow job 이름으로 표시됩니다. 목록에 보이지 않으면 먼저 `main`에 CI가 한 번 이상 성공적으로 실행되었는지 확인하세요.

## 운영 원칙

- CI가 통과하기 전에는 merge하지 않습니다.
- 실제 주문 기능, 실제 증권사 주문 API, 실제 계좌 조회 기능을 추가하는 PR은 merge하지 않습니다.
- `TossBrokerPlaceholder`를 실제 구현체로 바꾸는 PR은 명시적인 별도 승인 없이는 merge하지 않습니다.
- API Key, 토큰, 계좌정보, 실거래 데이터가 포함된 PR은 즉시 차단하고 secret rotation 필요 여부를 검토합니다.
- 공통 파일을 수정하는 PR은 `AGENTS.md`의 공유 파일 수정 규칙을 확인합니다.

## 수동 적용 체크리스트

- [ ] `main` branch protection rule 생성
- [ ] pull request required 활성화
- [ ] required status checks 활성화
- [ ] `CI` workflow 통과 필수 설정
- [ ] branch up-to-date before merge 설정 검토
- [ ] conversation resolution required 설정 검토
- [ ] force push 금지
- [ ] deletion 금지
- [ ] 관리자 동일 규칙 적용 여부 결정
