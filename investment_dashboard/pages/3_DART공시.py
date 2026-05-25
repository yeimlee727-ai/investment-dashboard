from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.dart.dart_client import DartClient
from src.ui_helpers import (
    format_display_dataframe,
    inject_global_css,
    render_data_warning,
    render_metric_card,
    render_page_header,
)


def main() -> None:
    st.set_page_config(page_title="DART 공시", layout="wide")
    inject_global_css()
    render_page_header(
        "DART 공시",
        "공시 유형, 위험 태그, 위험 점수를 필터링해 검토 필요 신호를 확인합니다.",
        badges=[("공시 리스크 점검", "info"), ("투자 실행 지시 아님", "success")],
    )
    render_data_warning()
    client = DartClient()
    if not client.has_api_key():
        st.warning("DART_API_KEY가 없어 샘플 데이터로 표시합니다.")

    col1, col2, col3 = st.columns(3)
    corp_code = col1.text_input("기업코드", placeholder="선택 입력")
    begin = col2.date_input("시작일", value=date.today() - timedelta(days=14))
    end = col3.date_input("종료일", value=date.today())
    disclosures = client.search_disclosures(
        corp_code=corp_code or None,
        begin=begin.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    disclosures = disclosures.copy()
    if "data_source" not in disclosures.columns:
        disclosures["data_source"] = "UNKNOWN"
    if "disclosure_type" not in disclosures.columns:
        disclosures["disclosure_type"] = "기타"
    if "risk_tag" not in disclosures.columns:
        disclosures["risk_tag"] = "neutral"
    if "risk_score" not in disclosures.columns:
        disclosures["risk_score"] = 38

    tag_counts = disclosures["risk_tag"].value_counts() if not disclosures.empty else {}
    cols = st.columns(4)
    metric_data = [
        ("critical", int(tag_counts.get("critical", 0)), "danger"),
        ("risk", int(tag_counts.get("risk", 0)), "warning"),
        ("caution", int(tag_counts.get("caution", 0)), "warning"),
        ("positive", int(tag_counts.get("positive", 0)), "success"),
    ]
    for col, (label, value, tone) in zip(cols, metric_data, strict=True):
        with col:
            render_metric_card(label, value, tone=tone)

    data_sources = set(disclosures["data_source"].astype(str))
    attr_source = str(disclosures.attrs.get("data_source", "UNKNOWN"))
    if {"SAMPLE_NO_API_KEY", "SAMPLE_FALLBACK"} & data_sources or attr_source in {
        "SAMPLE_NO_API_KEY",
        "SAMPLE_FALLBACK",
    }:
        st.warning("샘플 또는 fallback 공시입니다. 실제 DART 공시가 아닐 수 있습니다.")
    if "SAMPLE_FALLBACK" in data_sources or attr_source == "SAMPLE_FALLBACK":
        st.warning("DART API 조회 실패, 샘플 공시 표시 중입니다.")
    if disclosures.empty:
        if attr_source == "DART_API_NO_DATA":
            st.info("조회된 DART 공시가 없습니다.")
        else:
            st.info(f"조회된 DART 공시가 없습니다. data_source={attr_source}")
    type_options = (
        ["전체"] + sorted(disclosures["disclosure_type"].dropna().unique().tolist())
        if not disclosures.empty
        else ["전체"]
    )
    tag_options = (
        ["전체"] + sorted(disclosures["risk_tag"].dropna().unique().tolist())
        if not disclosures.empty
        else ["전체"]
    )
    source_options = (
        ["전체"] + sorted(disclosures["data_source"].dropna().unique().tolist())
        if not disclosures.empty
        else ["전체"]
    )
    with st.container(border=True):
        st.subheader("필터")
        filter_cols = st.columns(4)
        type_filter = filter_cols[0].selectbox("공시 유형 필터", type_options)
        tag_filter = filter_cols[1].selectbox("위험 태그 필터", tag_options)
        source_filter = filter_cols[2].selectbox("데이터 출처 필터", source_options)
        only_high_risk = filter_cols[3].checkbox("critical/risk만 보기")
    view = disclosures.copy()
    if type_filter != "전체":
        view = view[view["disclosure_type"] == type_filter]
    if tag_filter != "전체":
        view = view[view["risk_tag"] == tag_filter]
    if source_filter != "전체":
        view = view[view["data_source"] == source_filter]
    if only_high_risk:
        view = view[view["risk_tag"].isin(["critical", "risk"])]

    display_columns = [
        "stock_code",
        "corp_name",
        "rcept_dt",
        "report_nm",
        "disclosure_type",
        "risk_tag",
        "risk_score",
        "data_source",
        "url",
    ]
    display = view[[col for col in display_columns if col in view.columns]].rename(
        columns={
            "stock_code": "종목코드",
            "corp_name": "종목명",
            "rcept_dt": "공시일",
            "report_nm": "공시명",
            "url": "공시 링크",
        }
    )
    st.dataframe(
        format_display_dataframe(display),
        hide_index=True,
        width="stretch",
        column_config={
            "공시 링크": st.column_config.LinkColumn("공시 링크"),
            "위험 점수": st.column_config.TextColumn(
                "위험 점수",
                help="매수/매도 실행 지시가 아닌 검토 필요 위험 점수입니다.",
            ),
        },
    )

    st.subheader("기업코드 조회 구조")
    if st.button("기업코드 샘플/목록 불러오기"):
        codes = client.fetch_corp_codes()
        st.dataframe(codes.head(100), hide_index=True, width="stretch")


main()
