from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from io import BytesIO
import json
import math
from typing import Any
import zipfile

import pandas as pd

from src.broker.mock_broker import MockBroker
from src.risk.rebalancing_engine import RebalancingEngine, RebalancingResult
from src.scoring.portfolio_decision_engine import (
    PortfolioDecisionEngine,
    PortfolioDecisionResult,
)
from src.ui_helpers import localize_columns

REPORT_NOTICE = (
    "이 리포트는 MockBroker 가상 포지션 기반 의사결정 보조 정보입니다. "
    "실제 주문 기능 없음. 실제 체결, 실제 계좌 조회, 투자 추천을 제공하지 않습니다."
)

REPORT_LIMITATIONS = [
    "SAMPLE/FALLBACK 데이터는 실제 시장과 다를 수 있습니다.",
    "현재가는 외부 조회 또는 샘플 데이터 기반이며 실제 체결가가 아닐 수 있습니다.",
    "환율은 실제 증권사 환전 환율과 다를 수 있습니다.",
    "세금, 수수료, 슬리피지, 환전 스프레드는 실제와 차이가 있을 수 있습니다.",
    "실제 계좌 조회나 실제 주문 기능은 없습니다.",
    "리포트는 투자 판단 보조용이며 매수/매도 실행 지시가 아닙니다.",
]

FORBIDDEN_REPORT_WORDS = [
    "매수 추천",
    "매도 추천",
    "지금 사야",
    "지금 팔아",
    "수익 보장",
    "확정 전망",
    "주문 완료",
    "체결 완료",
]


@dataclass
class PortfolioReportData:
    generated_at: str
    data_mode: str
    provider_name: str
    report_info: pd.DataFrame
    summary: pd.DataFrame
    positions: pd.DataFrame
    strategy: pd.DataFrame
    scenarios: pd.DataFrame
    risk_rebalancing: pd.DataFrame
    correlation_summary: pd.DataFrame
    stress_test: pd.DataFrame
    allocation: pd.DataFrame
    limitations: pd.DataFrame
    decision_support_package: Any | None = None


def build_portfolio_report_data(
    positions: list[dict[str, Any]],
    portfolio_summary: dict[str, Any] | None = None,
    strategy_result: PortfolioDecisionResult | None = None,
    rebalancing_result: RebalancingResult | None = None,
    data_mode: str = "UNKNOWN",
    provider_name: str = "UNKNOWN",
    risk_profile: str = "균형 성장",
    additional_investment_krw: float = 3_000_000,
    decision_support_package: Any | None = None,
) -> PortfolioReportData:
    generated_at = datetime.now().isoformat(timespec="seconds")
    portfolio_summary = portfolio_summary or _summary_from_positions(positions)
    report_info = pd.DataFrame(
        [
            ("생성일시", generated_at),
            ("데이터 모드", data_mode),
            ("데이터 제공자", provider_name),
            ("리스크 프로필", risk_profile),
            ("입력 추가 투자금", additional_investment_krw),
            ("환율 상태", _fx_status_text(portfolio_summary)),
            ("안내", REPORT_NOTICE),
        ],
        columns=["항목", "값"],
    )
    summary = pd.DataFrame(
        [
            ("총 평가금액 KRW", portfolio_summary.get("total_market_value_krw")),
            ("총 매입금액 KRW", portfolio_summary.get("total_cost_basis_krw")),
            ("총 평가손익 KRW", portfolio_summary.get("total_unrealized_pnl_krw")),
            ("총 손익 KRW", portfolio_summary.get("total_pnl_krw")),
            ("총 손익률", portfolio_summary.get("total_pnl_pct")),
            ("보유 종목 수", portfolio_summary.get("position_count")),
            ("KR 비중", _weight_sum(positions, "KR")),
            ("US 비중", _weight_sum(positions, "US")),
            ("ETF / 개별주 비중", _asset_mix_text(strategy_result)),
            ("상위 1개 종목 비중", portfolio_summary.get("top1_weight_krw")),
            ("상위 3개 종목 비중", _summary_value(strategy_result, "top3_weight")),
            ("최대 수익 종목", portfolio_summary.get("max_profit_symbol")),
            ("최대 손실 종목", portfolio_summary.get("max_loss_symbol")),
            ("현재가 오류 건수", portfolio_summary.get("quote_error_count")),
            ("환율 오류 건수", portfolio_summary.get("fx_error_count")),
        ],
        columns=["항목", "값"],
    )
    strategy = (
        strategy_result.positions.copy()
        if strategy_result is not None
        else pd.DataFrame()
    )
    scenarios = (
        strategy_result.scenarios.copy()
        if strategy_result is not None
        else pd.DataFrame()
    )
    risk_rebalancing = _risk_rebalancing_frame(rebalancing_result)
    correlation_summary = _correlation_summary_frame(rebalancing_result)
    stress_test = (
        rebalancing_result.stress_results.copy()
        if rebalancing_result is not None
        else pd.DataFrame()
    )
    allocation = (
        rebalancing_result.allocation_plan.copy()
        if rebalancing_result is not None
        else pd.DataFrame()
    )
    limitations = pd.DataFrame({"제한사항": REPORT_LIMITATIONS})
    return PortfolioReportData(
        generated_at=generated_at,
        data_mode=data_mode,
        provider_name=provider_name,
        report_info=sanitize_report_dataframe(report_info),
        summary=sanitize_report_dataframe(summary),
        positions=sanitize_report_dataframe(pd.DataFrame(positions)),
        strategy=sanitize_report_dataframe(strategy),
        scenarios=sanitize_report_dataframe(scenarios),
        risk_rebalancing=sanitize_report_dataframe(risk_rebalancing),
        correlation_summary=sanitize_report_dataframe(correlation_summary),
        stress_test=sanitize_report_dataframe(stress_test),
        allocation=sanitize_report_dataframe(allocation),
        limitations=sanitize_report_dataframe(limitations),
        decision_support_package=decision_support_package,
    )


def build_report_from_provider(
    data_provider: Any,
    additional_investment_krw: float = 3_000_000,
    risk_profile: str = "균형 성장",
) -> PortfolioReportData:
    broker = MockBroker(data_provider=data_provider)
    positions = broker.get_positions()
    summary = broker.get_portfolio_summary()
    strategy_result = None
    rebalancing_result = None
    if positions:
        strategy_result = PortfolioDecisionEngine().analyze(positions, data_provider)
        rebalancing_result = RebalancingEngine().analyze(
            positions,
            data_provider,
            profile=risk_profile,
            additional_investment_krw=additional_investment_krw,
            decision_frame=strategy_result.positions,
        )
    return build_portfolio_report_data(
        positions=positions,
        portfolio_summary=summary,
        strategy_result=strategy_result,
        rebalancing_result=rebalancing_result,
        data_mode=str(getattr(data_provider, "mode", "UNKNOWN")),
        provider_name=str(data_provider.get_provider_name()),
        risk_profile=risk_profile,
        additional_investment_krw=additional_investment_krw,
    )


def build_report_sheets(report: PortfolioReportData) -> dict[str, pd.DataFrame]:
    return {
        "Summary": _with_empty_message(
            report.summary, "포트폴리오 요약 데이터가 없습니다."
        ),
        "Positions": _with_empty_message(
            report.positions, "가상 포지션 데이터가 없습니다."
        ),
        "Strategy": _with_empty_message(report.strategy, "전략분석 결과가 없습니다."),
        "Scenarios": _with_empty_message(report.scenarios, "시나리오 전망 데이터 없음"),
        "Correlation_Summary": _with_empty_message(
            report.correlation_summary, "상관관계 요약 데이터 없음"
        ),
        "Risk_Rebalancing": _with_empty_message(
            report.risk_rebalancing, "리스크·리밸런싱 결과가 없습니다."
        ),
        "Stress_Test": _with_empty_message(
            report.stress_test, "스트레스 테스트 결과가 없습니다."
        ),
        "Allocation": _with_empty_message(
            report.allocation, "추가 투자금 배분안이 없습니다."
        ),
        "Limitations": report.limitations,
        "Decision_Support": _decision_support_package_frame(
            getattr(report, "decision_support_package", None)
        ),
    }


def build_excel_report(report: PortfolioReportData) -> bytes:
    sheets = {"Report_Info": report.report_info, **build_report_sheets(report)}
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(list(sheets)))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (name, frame) in enumerate(sheets.items(), start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(name, sanitize_report_dataframe(frame)),
            )
    return output.getvalue()


def build_html_report(report: PortfolioReportData) -> str:
    sections = [
        ("리포트 기본 정보", report.report_info),
        ("포트폴리오 요약", report.summary),
    ]
    sections.extend(
        [
            ("모의매매 포지션 평가", report.positions),
            ("포트폴리오 전략분석", report.strategy),
            ("시나리오 전망 요약", report.scenarios),
            ("리스크·리밸런싱 분석", report.risk_rebalancing),
            ("상관관계 요약", report.correlation_summary),
            ("스트레스 테스트", report.stress_test),
            ("추가 투자금 배분안", report.allocation),
            ("제한사항", report.limitations),
        ]
    )
    body = "\n".join(
        f"<section><h2>{_escape_html(title)}</h2>{_frame_to_html(frame)}</section>"
        for title, frame in sections
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>포트폴리오 점검 리포트</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #111827; margin: 32px; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ border-bottom: 1px solid #d1d5db; padding-bottom: 6px; margin-top: 28px; }}
    .notice {{ background: #fef3c7; border: 1px solid #f59e0b; padding: 12px; border-radius: 6px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>포트폴리오 점검 리포트</h1>
  <p class="notice">{_escape_html(REPORT_NOTICE)}</p>
  {body}
</body>
</html>"""


def report_file_name(extension: str, generated_at: str | None = None) -> str:
    timestamp = generated_at or datetime.now().isoformat(timespec="minutes")
    safe = timestamp.replace("-", "").replace(":", "").replace("T", "_")
    return f"portfolio_report_{safe}.{extension.lstrip('.')}"


def sanitize_report_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    localized = localize_columns(frame.copy())
    if not isinstance(localized, pd.DataFrame):
        localized = frame.copy()
    clean = localized.replace([math.inf, -math.inf], pd.NA)
    clean = clean.where(pd.notna(clean), "계산 불가")
    for column in clean.columns:
        clean[column] = clean[column].map(format_report_value)
    return clean


def format_report_value(value: Any) -> Any:
    if value is None:
        return "계산 불가"
    if is_dataclass(value):
        return format_report_value(asdict(value))
    if isinstance(value, (dict, list, tuple, set)):
        return _format_nested_report_value(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "계산 불가"
    text = str(value)
    if text.strip().lower() in {"nan", "inf", "-inf", "none", "<na>"}:
        return "계산 불가"
    return value


def _format_nested_report_value(value: Any) -> str:
    def sanitize_nested(item: Any) -> Any:
        if item is None:
            return "계산 불가"
        if is_dataclass(item):
            return sanitize_nested(asdict(item))
        if isinstance(item, dict):
            return {str(key): sanitize_nested(nested) for key, nested in item.items()}
        if isinstance(item, (list, tuple, set)):
            return [sanitize_nested(nested) for nested in item]
        if isinstance(item, float) and (math.isnan(item) or math.isinf(item)):
            return "계산 불가"
        text = str(item)
        if text.strip().lower() in {"nan", "inf", "-inf", "none", "<na>"}:
            return "계산 불가"
        return item

    return json.dumps(sanitize_nested(value), ensure_ascii=False, sort_keys=True)


def _with_empty_message(frame: pd.DataFrame, message: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"안내": [message]})
    return frame


def _summary_from_positions(positions: list[dict[str, Any]]) -> dict[str, Any]:
    total_value = sum(_safe_float(row.get("market_value_krw")) for row in positions)
    total_cost = sum(_safe_float(row.get("cost_basis_krw")) for row in positions)
    total_unrealized = sum(
        _safe_float(row.get("unrealized_pnl_krw")) for row in positions
    )
    total_pnl = sum(_safe_float(row.get("total_pnl_krw")) for row in positions)
    return {
        "total_market_value_krw": total_value,
        "total_cost_basis_krw": total_cost,
        "total_unrealized_pnl_krw": total_unrealized,
        "total_pnl_krw": total_pnl,
        "total_pnl_pct": total_pnl / total_cost * 100 if total_cost else None,
        "position_count": len(positions),
        "top1_weight_krw": max(
            [_safe_float(row.get("position_weight_krw")) for row in positions],
            default=0.0,
        ),
        "quote_error_count": sum(1 for row in positions if row.get("quote_error")),
        "fx_error_count": sum(1 for row in positions if row.get("fx_error")),
    }


def _risk_rebalancing_frame(result: RebalancingResult | None) -> pd.DataFrame:
    if result is None:
        return pd.DataFrame()
    parts = []
    if not result.risk_contribution.empty:
        parts.append(result.risk_contribution)
    if not result.target_comparison.empty:
        parts.append(result.target_comparison)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True, sort=False)


def _correlation_summary_frame(result: RebalancingResult | None) -> pd.DataFrame:
    if result is None:
        return pd.DataFrame()
    summary = result.correlation_summary
    rows = [
        ("평균 상관관계", summary.get("average_correlation")),
        ("최고 상관 종목쌍", summary.get("highest_pair")),
        ("최고 상관계수", summary.get("highest_correlation")),
        ("최저 상관 종목쌍", summary.get("lowest_pair")),
        ("최저 상관계수", summary.get("lowest_correlation")),
        ("분산 효과 코멘트", summary.get("diversification_comment")),
    ]
    return pd.DataFrame(rows, columns=["항목", "값"])


def _decision_support_package_frame(package: Any | None) -> pd.DataFrame:
    if package is None:
        return pd.DataFrame(
            [
                (
                    "Decision_Support",
                    "Status",
                    "Decision support package data not available",
                )
            ],
            columns=["Section", "Field", "Value"],
        )
    data = _package_to_dict(package)
    if not data:
        return pd.DataFrame(
            [
                (
                    "Decision_Support",
                    "Status",
                    "Decision support package data not available",
                )
            ],
            columns=["Section", "Field", "Value"],
        )

    rows: list[tuple[str, str, Any]] = [
        ("Package", "package_version", data.get("package_version")),
        ("Package", "data_status", data.get("data_status")),
        ("Package", "markdown_available", bool(data.get("markdown"))),
    ]
    for flag, value in sorted(_as_dict(data.get("safety_flags")).items()):
        rows.append(("Safety_Flags", flag, value))

    included_sections, missing_sections = _decision_support_section_status(data)
    rows.append(("Included_Sections", "sections", included_sections))
    rows.append(("Missing_Sections", "sections", missing_sections))

    candidate_summary = _as_dict(data.get("candidate_score_summary"))
    rows.extend(
        [
            ("Candidate_Review", "total_count", candidate_summary.get("total_count")),
            ("Candidate_Review", "top_symbols", candidate_summary.get("top_symbols")),
            (
                "Candidate_Review",
                "caution_symbols",
                candidate_summary.get("caution_symbols"),
            ),
            ("Candidate_Review", "summary_note", candidate_summary.get("summary_note")),
        ]
    )
    fit_summary = _as_dict(data.get("portfolio_fit_summary"))
    rows.extend(
        [
            ("Portfolio_Fit", "total_count", fit_summary.get("total_count")),
            ("Portfolio_Fit", "top_fit_symbols", fit_summary.get("top_fit_symbols")),
            (
                "Portfolio_Fit",
                "concentration_caution_symbols",
                fit_summary.get("concentration_caution_symbols"),
            ),
            ("Portfolio_Fit", "summary_note", fit_summary.get("summary_note")),
        ]
    )
    action_summary = _as_dict(data.get("action_plan_summary"))
    rows.extend(
        [
            ("Action_Plans", "total_count", action_summary.get("total_count")),
            (
                "Action_Plans",
                "ready_for_manual_review_count",
                action_summary.get("ready_for_manual_review_count"),
            ),
            (
                "Action_Plans",
                "top_review_symbols",
                action_summary.get("top_review_symbols"),
            ),
            ("Action_Plans", "caution_symbols", action_summary.get("caution_symbols")),
            ("Action_Plans", "summary_note", action_summary.get("summary_note")),
        ]
    )
    for index, limitation in enumerate(_as_list(data.get("limitations")), start=1):
        rows.append(("Limitations", f"limitation_{index}", limitation))

    return sanitize_report_dataframe(
        pd.DataFrame(rows, columns=["Section", "Field", "Value"])
    )


def _package_to_dict(package: Any) -> dict[str, Any]:
    if is_dataclass(package):
        package = asdict(package)
    if isinstance(package, dict):
        return package
    return {}


def _as_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        value = asdict(value)
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _decision_support_section_status(
    data: dict[str, Any],
) -> tuple[list[str], list[str]]:
    section_names = [
        "portfolio_context",
        "risk_insight_summary",
        "investment_map_summary",
        "candidate_score_summary",
        "portfolio_fit_summary",
        "insight_report",
        "action_plan_summary",
        "action_plans",
        "market_regime_context",
    ]
    included = [name for name in section_names if _has_package_value(data.get(name))]
    missing = [name for name in section_names if not _has_package_value(data.get(name))]
    return included, missing


def _has_package_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _fx_status_text(summary: dict[str, Any]) -> str:
    rate = summary.get("fx_rate")
    source = summary.get("fx_data_source")
    error = summary.get("fx_error")
    if error:
        return f"환율 오류: {error}"
    if rate:
        return f"USD/KRW {rate} ({source or 'UNKNOWN'})"
    return "환율 정보 없음"


def _weight_sum(positions: list[dict[str, Any]], market: str) -> float | None:
    values = [
        _safe_float(row.get("position_weight_krw"))
        for row in positions
        if str(row.get("market")) == market
    ]
    return round(sum(values), 2) if values else None


def _asset_mix_text(strategy_result: PortfolioDecisionResult | None) -> str:
    if strategy_result is None:
        return "계산 불가"
    summary = strategy_result.portfolio_summary
    return (
        f"ETF {summary.get('etf_weight', '계산 불가')}% / "
        f"개별주 {summary.get('stock_weight', '계산 불가')}%"
    )


def _summary_value(
    strategy_result: PortfolioDecisionResult | None, key: str
) -> Any | None:
    if strategy_result is None:
        return None
    return strategy_result.portfolio_summary.get(key)


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _content_types_xml(sheet_count: int) -> str:
    worksheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{worksheets}
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{_escape_xml(name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>{sheets}</sheets>
</workbook>"""


def _workbook_rels_xml(sheet_count: int) -> str:
    sheets = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, sheet_count + 1)
    )
    style_id = sheet_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{sheets}
<Relationship Id="rId{style_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""


def _worksheet_xml(title: str, frame: pd.DataFrame) -> str:
    rows = [[title], [REPORT_NOTICE], [], list(frame.columns)]
    rows.extend(frame.astype(str).values.tolist())
    max_widths = _column_widths(rows)
    cols = "".join(
        f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>'
        for i, width in enumerate(max_widths, start=1)
    )
    xml_rows = "".join(_row_xml(index, row) for index, row in enumerate(rows, start=1))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<cols>{cols}</cols>
<sheetData>{xml_rows}</sheetData>
</worksheet>"""


def _row_xml(row_index: int, row: list[Any]) -> str:
    cells = "".join(
        _cell_xml(row_index, column_index, value)
        for column_index, value in enumerate(row, start=1)
    )
    return f'<row r="{row_index}">{cells}</row>'


def _cell_xml(row_index: int, column_index: int, value: Any) -> str:
    ref = f"{_column_letter(column_index)}{row_index}"
    return f'<c r="{ref}" t="inlineStr"><is><t>{_escape_xml(str(value))}</t></is></c>'


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _column_widths(rows: list[list[Any]]) -> list[int]:
    max_columns = max((len(row) for row in rows), default=1)
    widths = []
    for column_index in range(max_columns):
        width = max(
            [len(str(row[column_index])) for row in rows if column_index < len(row)]
            or [10]
        )
        widths.append(min(max(width + 2, 12), 48))
    return widths


def _frame_to_html(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "<p>표시할 데이터가 없습니다.</p>"
    return sanitize_report_dataframe(frame).to_html(index=False, escape=True)


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _escape_html(value: str) -> str:
    return _escape_xml(value)
