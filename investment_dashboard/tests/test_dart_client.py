from __future__ import annotations

import pytest
import pandas as pd

from src.dart import dart_client
from src.dart.dart_client import (
    DartClient,
    aggregate_disclosure_risk,
    classify_disclosure,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


def test_no_api_key_uses_sample_no_api_key() -> None:
    result = DartClient(api_key=None).search_disclosures()
    assert result["data_source"].unique().tolist() == ["SAMPLE_NO_API_KEY"]


def test_api_error_uses_sample_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(*args, **kwargs):
        raise RuntimeError("network")

    monkeypatch.setattr(dart_client.requests, "get", raise_error)
    result = DartClient(api_key="key").search_disclosures()
    assert result["data_source"].unique().tolist() == ["SAMPLE_FALLBACK"]


def test_api_no_data_returns_empty_dart_api_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dart_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"status": "013", "list": []}),
    )
    result = DartClient(api_key="key").search_disclosures()
    assert result.empty
    assert result.attrs["data_source"] == "DART_API_NO_DATA"


def test_api_success_returns_dart_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dart_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {
                "status": "000",
                "list": [
                    {
                        "corp_name": "테스트",
                        "stock_code": "123456",
                        "report_nm": "단일판매ㆍ공급계약체결",
                        "rcept_dt": "20260501",
                        "rcept_no": "202605010001",
                    }
                ],
            }
        ),
    )
    result = DartClient(api_key="key").search_disclosures()
    assert result["data_source"].unique().tolist() == ["DART_API"]
    assert result.iloc[0]["disclosure_type"] == "공급계약"
    assert result.iloc[0]["risk_tag"] == "positive"
    assert result.iloc[0]["risk_score"] == 15


@pytest.mark.parametrize(
    ("report_name", "expected_type", "expected_tag", "min_score", "max_score"),
    [
        ("단일판매ㆍ공급계약체결", "공급계약", "positive", 10, 25),
        ("자기주식취득결정", "자기주식취득", "positive", 10, 25),
        ("현금배당 결정", "현금배당", "positive", 10, 25),
        ("무상증자 결정", "무상증자", "positive", 10, 25),
        ("신규시설투자", "신규시설투자", "neutral", 30, 45),
        ("유상증자 결정", "유상증자", "caution", 50, 70),
        ("전환사채권발행결정", "전환사채", "caution", 50, 70),
        ("신주인수권부사채권발행결정", "신주인수권부사채", "caution", 50, 70),
        ("교환사채권발행결정", "교환사채", "caution", 50, 70),
        ("최대주주 변경", "최대주주변경", "caution", 50, 70),
        ("소송 등의 제기", "소송", "risk", 70, 85),
        ("영업정지", "영업정지", "risk", 70, 85),
        ("불성실공시법인지정", "불성실공시", "risk", 70, 85),
        ("감사보고서 제출", "감사의견", "neutral", 30, 45),
        ("영업이익 잠정실적 공시", "실적공시", "neutral", 30, 45),
        ("감사보고서 의견거절", "감사의견", "critical", 90, 100),
        ("감사보고서 한정", "감사의견", "risk", 70, 85),
        ("감사보고서 부적정", "감사의견", "critical", 90, 100),
        ("감사보고서 계속기업 불확실성", "감사의견", "critical", 90, 100),
        ("횡령ㆍ배임 혐의 발생", "횡령배임", "critical", 90, 100),
        ("상장폐지 사유 발생", "감사의견", "critical", 90, 100),
        ("거래정지", "거래위험", "critical", 90, 100),
        ("회생절차 개시신청", "회생절차", "critical", 90, 100),
        ("자본잠식 발생", "자본잠식", "critical", 90, 100),
    ],
)
def test_disclosure_classification(
    report_name: str,
    expected_type: str,
    expected_tag: str,
    min_score: int,
    max_score: int,
) -> None:
    disclosure_type, risk_tag, risk_score = classify_disclosure(report_name)
    assert disclosure_type == expected_type
    assert risk_tag == expected_tag
    assert min_score <= risk_score <= max_score


def test_aggregate_disclosure_risk_critical_cannot_be_offset() -> None:
    disclosures = dart_client.enrich_disclosures(
        pd.DataFrame(
            [
                {
                    "stock_code": "123456",
                    "corp_name": "테스트",
                    "report_nm": "상장폐지 사유 발생",
                    "rcept_dt": "20260501",
                },
                {
                    "stock_code": "123456",
                    "corp_name": "테스트",
                    "report_nm": "현금배당 결정",
                    "rcept_dt": "20260502",
                },
            ]
        ),
        "DART_API",
    )
    aggregate = aggregate_disclosure_risk(disclosures)
    assert aggregate.iloc[0]["aggregate_risk_tag"] == "critical"
    assert aggregate.iloc[0]["aggregate_risk_score"] >= 90


def test_aggregate_disclosure_risk_recent_cautions_add_weight() -> None:
    disclosures = dart_client.enrich_disclosures(
        pd.DataFrame(
            [
                {
                    "stock_code": "654321",
                    "corp_name": "테스트",
                    "report_nm": "유상증자 결정",
                    "rcept_dt": "20260501",
                },
                {
                    "stock_code": "654321",
                    "corp_name": "테스트",
                    "report_nm": "전환사채권발행결정",
                    "rcept_dt": "20260503",
                },
            ]
        ),
        "DART_API",
    )
    aggregate = aggregate_disclosure_risk(disclosures)
    assert aggregate.iloc[0]["aggregate_risk_tag"] in {"caution", "risk"}
    assert aggregate.iloc[0]["recent_caution_count"] == 2
