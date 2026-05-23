# 개인용 투자 대시보드 MVP

Python과 Streamlit으로 만든 개인용 투자 리서치 대시보드입니다.

현재 버전은 토스증권 API와 실제 주문 기능을 사용하지 않습니다. 향후 API 승인이 되었을 때 연결하기 쉽도록 `Broker`와 `DataProvider` 어댑터 구조만 준비되어 있으며, 실제 주문은 `MockBroker`의 가상 주문으로만 처리됩니다.

> 중요: 기본 가격 데이터는 실제 시세가 아닌 샘플 데이터입니다. 이 앱은 실제 주문을 전송하지 않으며, 투자 판단용 도구가 아닙니다.

## 기능

- 다크 테마 Streamlit 대시보드
- 국내주식/미국주식 관심종목 관리
- SQLite 기반 데이터 저장
- 교체 가능한 가격 데이터 공급자 구조
- DART Open API 공시 검색 구조
- API 키가 없을 때 샘플 공시 데이터 자동 사용
- RSI, EMA 20/60, MACD, ATR, 거래량 이동평균, 신고가 근접률 계산
- 종목 스캐너와 100점 점수화
- AI 코멘트 생성용 프롬프트 문자열 생성
- CSV 또는 샘플 데이터 기반 백테스트
- 실제 주문 없는 모의매매
- 주문 한도, 종목별 한도, 일 손실 한도, 중복 진입 방지, 비상정지 리스크 체크

## 데이터 모드

사이드바에서 가격 데이터 모드를 선택할 수 있습니다. 기본값은 항상 `SAMPLE`입니다.

- `SAMPLE`: `SampleDataProvider`가 생성한 결정적 샘플 데이터를 사용합니다. 같은 종목은 재실행해도 같은 형태의 샘플 가격 데이터를 생성합니다.
- `REAL_WITH_FALLBACK`: 조회용 외부 provider를 먼저 시도하고, 실패하거나 데이터가 비어 있으면 `SampleDataProvider`로 자동 fallback합니다.

현재 조회용 외부 provider는 미국 주식에 한해 `yfinance`를 사용합니다. 국내 주식 실시간/조회용 provider는 아직 연결하지 않았으며, `REAL_WITH_FALLBACK`에서도 국내 주식은 샘플 fallback이 발생할 수 있습니다.

외부 시세 데이터는 다음 한계가 있습니다.

- 거래소 공식 실시간 시세가 아닐 수 있으며 지연될 수 있습니다.
- 라이브러리, 네트워크, 심볼 형식, 데이터 제공 정책에 따라 오류나 빈 데이터가 발생할 수 있습니다.
- 개발/테스트용 조회 기능이며 투자 판단, 주문 판단, 수익 보장에 사용할 수 없습니다.
- 실제 주문 기능은 여전히 없으며, `MockBroker`는 가상 주문만 처리하고 `TossBrokerPlaceholder`는 placeholder 상태입니다.

## SAMPLE MODE와 백테스트 한계

- 기본 가격 데이터는 `SampleDataProvider`가 생성한 가상 OHLCV 데이터입니다.
- SAMPLE MODE 결과는 실제 시세, 실제 거래량, 실제 체결 가능성을 반영하지 않습니다.
- 백테스트는 리서치용 시뮬레이션이며 투자 판단이나 수익 보장을 의미하지 않습니다.
- 백테스트 신규 진입은 신호 다음 봉의 시가로 처리하며 마지막 봉에서는 새로 진입하지 않습니다.
- 손절/익절 판정은 화면에서 `종가 기준` 또는 `장중 터치 기준`으로 선택할 수 있습니다.
- 장중 터치 기준에서 같은 봉에 손절과 익절이 동시에 발생하면 보수적으로 손절을 먼저 처리합니다.
- 수수료와 슬리피지는 단순 비율 모델이며 실제 증권사 체결, 세금, 호가 공백, 유동성 부족을 완전히 반영하지 않습니다.

## 설치

Python 3.11 이상을 권장합니다.

### Windows PowerShell

```powershell
cd investment_dashboard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

개발/테스트 도구까지 설치하려면 아래 명령을 사용합니다.

```powershell
pip install -r requirements-dev.txt
```

### Windows CMD

```cmd
cd investment_dashboard
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

개발/테스트 도구까지 설치하려면 아래 명령을 사용합니다.

```cmd
pip install -r requirements-dev.txt
```

### macOS/Linux

```bash
cd investment_dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

개발/테스트 도구까지 설치하려면 아래 명령을 사용합니다.

```bash
pip install -r requirements-dev.txt
```

## 환경 변수

`.env.example` 파일을 복사해서 `.env`를 만듭니다.

```bash
copy .env.example .env
```

DART API 키가 있으면 `.env`에 입력합니다.

```text
DART_API_KEY=발급받은키
DATABASE_URL=sqlite:///db/investment_dashboard.sqlite3
```

키가 없어도 앱은 샘플 공시 데이터로 정상 실행됩니다.

## 실행

### Windows PowerShell 또는 CMD

```powershell
streamlit run app.py
```

### macOS/Linux

```bash
streamlit run app.py
```

브라우저에서 표시되는 로컬 주소로 접속하면 됩니다.

## 개발 중 DB 초기화

개발 단계에서는 `models.py`의 테이블 구조가 바뀌면 기존 SQLite DB와 충돌할 수 있습니다.
컬럼 추가, 타입 변경, 테이블 추가 후 실행 오류가 발생하면 앱을 종료한 뒤 아래 파일을 삭제하고 다시 실행하세요.

```text
db/investment_dashboard.sqlite3
```

파일을 삭제한 뒤 `streamlit run app.py`를 다시 실행하면 SQLite DB가 현재 모델 기준으로 재생성됩니다.

## 테스트와 품질 검증

외부 API나 실제 증권사 연결 없이 샘플/fake/mock 데이터만 사용해 테스트합니다.

```bash
pip install -r requirements-dev.txt
python -m compileall .
python scripts/verify_compile.py
python -m pytest -vv
ruff check .
black --check .
```

GitHub Actions CI도 같은 품질 검증을 수행합니다. `main` 브랜치에 push하거나 pull request를 열면 자동으로 Python 3.11 환경에서 의존성을 설치하고 `compileall`, `python -m pytest -vv`, `ruff`, `black --check`를 실행합니다.

주요 테스트 범위는 다음과 같습니다.

- `MockBroker` 가상 매수/매도, rejected 처리, KR/US 가격 조회, 실현손익 로그
- `RiskEngine` 주문 한도, 종목 한도, 일 손실 한도, 중복 진입, 비상정지
- `BacktestEngine` 다음 봉 시가 진입, 마지막 봉 진입 방지, 수수료/슬리피지, 포지션 비중, 손절/익절 판정
- 기술지표 RSI/EMA/MACD/ATR/거래량 이동평균
- 스캐너/점수화/DART 공시 분류
- 데이터 provider 인터페이스, SAMPLE 모드, REAL_WITH_FALLBACK 샘플 fallback

## 프로젝트 구조

```text
investment_dashboard/
├─ app.py
├─ requirements.txt
├─ requirements-dev.txt
├─ README.md
├─ .env.example
├─ data/
├─ db/
├─ scripts/
├─ src/
│  ├─ config.py
│  ├─ database.py
│  ├─ models.py
│  ├─ data_providers/
│  ├─ dart/
│  ├─ indicators/
│  ├─ scanner/
│  ├─ scoring/
│  ├─ backtest/
│  ├─ broker/
│  └─ risk/
└─ pages/
└─ tests/
```

## 중요한 제한 사항

- 기본 실행 모드는 `SAMPLE MODE`이며 가격, 거래량, 거래대금, 등락률은 실제 시세가 아닐 수 있습니다.
- `REAL_WITH_FALLBACK` 모드의 외부 시세도 지연, 누락, 오류가 있을 수 있으며 투자 판단용이 아닙니다.
- 이 앱의 점수, 스캐너, 백테스트, AI 코멘트 프롬프트는 투자 추천이나 매수/매도 신호가 아닙니다.
- 이 MVP에는 실제 매매 주문 코드가 없습니다.
- `MockBroker`는 SQLite에 가상 주문과 가상 포지션만 저장합니다.
- `TossBrokerPlaceholder`는 의도적으로 `NotImplementedError`만 발생시키는 자리표시자입니다.
- 실전 투자 판단, 세무 판단, 법적 판단, 재무 자문 용도로 사용하면 안 됩니다.

## Git/ZIP 제외 파일

다음 항목은 `.gitignore`에 포함되어 Git이나 배포 ZIP에 넣지 않는 것을 권장합니다.

- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `*.pyc`, `*.pyo`, `*.pyd`
- `*.log`
- `db/*.sqlite3`, `db/*.sqlite`
- `.env`
- `.streamlit/secrets.toml`

## 절대 업로드하면 안 되는 파일

- 실제 API 키가 들어 있는 `.env`
- Streamlit 비밀값 파일 `.streamlit/secrets.toml`
- 개인 로컬 가상환경 `.venv/`
- 로컬 SQLite DB 파일 `db/*.sqlite3`, `db/*.sqlite`
- 실행 로그나 개인 경로가 포함된 `*.log`
- 증권사 API 토큰, 계좌번호, 개인 인증정보가 들어간 모든 파일

GitHub 또는 ZIP 공유 전에는 저장소에 위 파일들이 들어가지 않았는지 반드시 확인하세요.

## 향후 Toss API 연결 위치

- 실제 브로커 연결: `src/broker/toss_broker_placeholder.py`
- 브로커 공통 인터페이스: `src/broker/base.py`
- 가격 데이터 공급자 교체: `src/data_providers/market_data_provider.py`

토스 API 승인 후에도 UI와 백테스트/스캐너 로직을 크게 바꾸지 않고 어댑터 내부만 구현하는 구조입니다.
