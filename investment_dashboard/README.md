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

## 설치

Python 3.11 이상을 권장합니다.

### Windows PowerShell

```powershell
cd investment_dashboard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Windows CMD

```cmd
cd investment_dashboard
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### macOS/Linux

```bash
cd investment_dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## 프로젝트 구조

```text
investment_dashboard/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .env.example
├─ data/
├─ db/
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
```

## 중요한 제한 사항

- 기본 실행 모드는 `SAMPLE MODE`이며 가격, 거래량, 거래대금, 등락률은 실제 시세가 아닐 수 있습니다.
- 이 앱의 점수, 스캐너, 백테스트, AI 코멘트 프롬프트는 투자 추천이나 매수/매도 신호가 아닙니다.
- 이 MVP에는 실제 매매 주문 코드가 없습니다.
- `MockBroker`는 SQLite에 가상 주문과 가상 포지션만 저장합니다.
- `TossBrokerPlaceholder`는 의도적으로 `NotImplementedError`만 발생시키는 자리표시자입니다.
- 실전 투자 판단, 세무 판단, 법적 판단, 재무 자문 용도로 사용하면 안 됩니다.

## Git/ZIP 제외 파일

다음 항목은 `.gitignore`에 포함되어 Git이나 배포 ZIP에 넣지 않는 것을 권장합니다.

- `.venv/`
- `__pycache__/`
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
