from __future__ import annotations

import streamlit as st

from src.data_providers.base import DataMode
from src.data_providers.market_data_provider import MarketDataProvider

KOREAN_COLUMN_LABELS = {
    "symbol": "종목코드",
    "name": "종목명",
    "market": "시장",
    "sector": "섹터",
    "memo": "메모",
    "latest_price": "최근가",
    "change_pct": "등락률(%)",
    "data_source": "데이터 출처",
    "provider": "데이터 제공자",
    "quote_error": "시세 오류",
    "as_of": "기준시각",
    "score": "점수",
    "volume_ratio": "거래량 비율",
    "risk_tag": "리스크 태그",
    "risk_penalty": "리스크 감점",
    "currency": "통화",
    "quantity": "수량",
    "avg_price": "평균단가",
    "current_price": "현재가",
    "market_value": "평가금액",
    "market_value_krw": "평가금액(원화)",
    "cost_basis": "매입금액",
    "cost_basis_krw": "매입금액(원화)",
    "unrealized_pnl": "평가손익",
    "unrealized_pnl_krw": "평가손익(원화)",
    "unrealized_pnl_pct": "평가손익률(%)",
    "realized_pnl": "실현손익",
    "realized_pnl_krw": "실현손익(원화)",
    "realized_pnl_pct": "실현손익률(%)",
    "total_pnl": "총손익",
    "total_pnl_krw": "총손익(원화)",
    "total_pnl_pct": "총손익률(%)",
    "position_weight": "비중",
    "position_weight_krw": "비중(원화 기준)",
    "fx_rate": "환율",
    "fx_data_source": "환율 출처",
    "fx_error": "환율 오류",
    "updated_at": "갱신시각",
    "created_at": "생성시각",
    "side": "구분",
    "price": "가격",
    "status": "상태",
    "reason": "사유",
    "error_message": "오류 메시지",
    "realized_at": "실현시각",
    "entry_price": "진입가",
    "exit_price": "청산가",
    "holding_days": "보유일수",
    "exit_reason": "청산사유",
    "ticker": "종목",
    "corp_name": "기업명",
    "stock_code": "종목코드",
    "report_nm": "공시명",
    "risk_score": "위험 점수",
    "trend_status": "추세 상태",
    "data_days": "데이터 일수",
    "data_years": "데이터 기간(년)",
    "reliability": "신뢰도",
    "reliability_reason": "신뢰도 사유",
    "return_1m": "1개월 수익률(%)",
    "return_3m": "3개월 수익률(%)",
    "return_6m": "6개월 수익률(%)",
    "return_1y": "1년 수익률(%)",
    "return_3y": "3년 수익률(%)",
    "cumulative_return": "누적 수익률(%)",
    "annualized_volatility": "연환산 변동성(%)",
    "mdd": "MDD(%)",
    "drawdown_from_52w_high": "52주 고점 대비(%)",
    "rebound_from_52w_low": "52주 저점 대비(%)",
    "ma20_position": "20일선 대비(%)",
    "ma60_position": "60일선 대비(%)",
    "ma120_position": "120일선 대비(%)",
    "ma240_position": "240일선 대비(%)",
    "rsi": "RSI",
    "additional_buy_score": "추가매수 점수",
    "additional_buy_opinion": "추가매수 의견",
    "sell_review_score": "매도검토 점수",
    "sell_review_opinion": "매도검토 의견",
    "decision_comment": "분석 코멘트",
    "upside": "상승 시나리오",
    "neutral": "중립 시나리오",
    "downside": "하락 시나리오",
    "페이지": "페이지",
    "설명": "설명",
}


def korean_column_name(column: str) -> str:
    return KOREAN_COLUMN_LABELS.get(column, column)


def localize_columns(
    rows_or_frame: object,
) -> object:
    if hasattr(rows_or_frame, "rename"):
        return rows_or_frame.rename(columns=KOREAN_COLUMN_LABELS)  # type: ignore[no-any-return]
    if isinstance(rows_or_frame, list):
        return [
            {korean_column_name(str(key)): value for key, value in row.items()}
            for row in rows_or_frame
            if isinstance(row, dict)
        ]
    return rows_or_frame


def mock_delete_warning_message() -> str:
    return (
        "이 삭제 기능은 MockBroker 기반 테스트 데이터 정리용입니다. "
        "실제 주문, 실제 체결, 실제 계좌와는 무관합니다."
    )


def get_data_mode_status(
    mode: DataMode,
    is_fallback: bool = False,
) -> tuple[str, str, str]:
    if mode == "REAL_WITH_FALLBACK" and is_fallback:
        return (
            "FALLBACK MODE",
            "외부 조회 실패로 샘플 데이터를 표시 중입니다.",
            "warning",
        )
    if mode == "REAL_WITH_FALLBACK":
        return (
            "REAL DATA MODE",
            "외부 조회 데이터를 사용 중입니다. 지연/오차 가능성이 있습니다.",
            "info",
        )
    return (
        "SAMPLE MODE",
        "실제 시세가 아닌 샘플 데이터입니다.",
        "warning",
    )


def format_profit_factor(value: float) -> str:
    if value >= 999:
        return "999+ (손실 거래 없음)"
    return f"{value:.2f}"


def format_avg_profit_loss_ratio(value: float, profit_factor: float) -> str:
    if profit_factor >= 999:
        return "N/A (손실 거래 없음)"
    return f"{value:.2f}"


def get_backtest_warning_messages(
    trade_count: int,
    profit_factor: float,
    avg_profit_loss_ratio: float,
    data_source: str | None = None,
) -> list[str]:
    messages = []
    if trade_count < 10:
        messages.append(
            "거래 횟수가 적어 통계적 신뢰도가 낮습니다. "
            "이 결과만으로 전략 성과를 판단하지 마세요."
        )
    if profit_factor >= 999:
        messages.append(
            "손실 거래가 없어 Profit factor가 과도하게 높게 보일 수 있습니다. "
            "표시는 999+로 제한합니다."
        )
    if profit_factor >= 999 or avg_profit_loss_ratio == 0:
        messages.append("N/A: 손실 거래가 없어 평균 손익비 계산이 제한됩니다.")
    if data_source in {"SAMPLE", "SAMPLE_FALLBACK"}:
        messages.append(
            "SAMPLE/FALLBACK 데이터 기반 결과는 실제 시장 성과와 다를 수 있습니다."
        )
    return messages


def get_fx_status_message(
    rate: float | None, data_source: str, error: str | None
) -> str:
    if rate is None:
        return "환율 조회 실패로 US 종목의 원화 환산 평가가 제한됩니다."
    if error:
        return (
            f"USD/KRW {rate:,.2f}을 사용합니다. "
            f"{data_source} 기준이며 외부 환율 조회 오류가 있었습니다: {error}"
        )
    return f"USD/KRW {rate:,.2f}을 사용합니다. 출처: {data_source}"


def select_data_mode() -> DataMode:
    selected = st.sidebar.radio(
        "데이터 모드",
        ["SAMPLE", "REAL_WITH_FALLBACK"],
        index=0,
        help=(
            "SAMPLE은 생성된 샘플 데이터를 사용합니다. "
            "REAL_WITH_FALLBACK은 외부 시세 조회를 시도하고 실패하면 샘플 데이터를 표시합니다."
        ),
    )
    return selected  # type: ignore[return-value]


def build_market_data_provider() -> MarketDataProvider:
    return MarketDataProvider(mode=select_data_mode())


def render_data_warning(provider: MarketDataProvider | None = None) -> None:
    provider = provider or build_market_data_provider()
    badge, message, level = get_data_mode_status(
        provider.mode, provider.is_fallback_mode()
    )
    st.markdown(f"`{badge}`")
    if level == "info":
        st.info(f"{badge}: {message} 실제 주문 기능은 포함되어 있지 않습니다.")
    else:
        st.warning(
            f"{badge}: {message} "
            "이 앱은 실제 주문을 하지 않으며 투자 판단용으로 사용하면 안 됩니다."
        )
