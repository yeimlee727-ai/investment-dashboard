from __future__ import annotations

import pytest

from src.dart import dart_client
from src.dart.dart_client import DartClient, classify_disclosure


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
    assert result.iloc[0]["risk_tag"] == "긍정"


@pytest.mark.parametrize(
    ("report_name", "expected_type", "expected_tag"),
    [
        ("단일판매ㆍ공급계약체결", "공급계약", "긍정"),
        ("유상증자 결정", "유상증자", "주의"),
        ("전환사채권발행결정", "전환사채", "주의"),
        ("자기주식취득결정", "자기주식", "긍정"),
        ("최대주주 변경", "최대주주변경", "주의"),
        ("소송 등의 제기", "소송", "위험"),
        ("감사보고서 제출", "감사의견", "중립"),
        ("영업이익 잠정실적 공시", "실적공시", "중립"),
        ("감사보고서 의견거절", "감사의견", "위험"),
        ("감사보고서 한정", "감사의견", "위험"),
        ("감사보고서 부적정", "감사의견", "위험"),
        ("감사보고서 계속기업 불확실성", "감사의견", "위험"),
    ],
)
def test_disclosure_classification(
    report_name: str, expected_type: str, expected_tag: str
) -> None:
    assert classify_disclosure(report_name) == (expected_type, expected_tag)
