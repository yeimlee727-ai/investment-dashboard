from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.dart.dart_client import DartClient
from src.ui_helpers import render_data_warning


def main() -> None:
    st.set_page_config(page_title="DART 공시", layout="wide")
    st.title("DART 공시")
    render_data_warning()
    client = DartClient()
    if not client.has_api_key():
        st.warning("DART_API_KEY가 없어 샘플 데이터로 표시합니다.")

    col1, col2, col3 = st.columns(3)
    corp_code = col1.text_input("기업코드", placeholder="선택 입력")
    begin = col2.date_input("시작일", value=date.today() - timedelta(days=14))
    end = col3.date_input("종료일", value=date.today())
    disclosures = client.search_disclosures(corp_code=corp_code or None, begin=begin.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
    if not disclosures.empty and "SAMPLE_FALLBACK" in set(disclosures["data_source"].astype(str)):
        st.warning("DART API 조회 실패, 샘플 공시 표시 중입니다.")
    type_options = ["전체"] + sorted(disclosures["disclosure_type"].dropna().unique().tolist()) if not disclosures.empty else ["전체"]
    tag_options = ["전체"] + sorted(disclosures["risk_tag"].dropna().unique().tolist()) if not disclosures.empty else ["전체"]
    type_filter = st.selectbox("공시 유형 필터", type_options)
    tag_filter = st.selectbox("태그 필터", tag_options)
    view = disclosures.copy()
    if type_filter != "전체":
        view = view[view["disclosure_type"] == type_filter]
    if tag_filter != "전체":
        view = view[view["risk_tag"] == tag_filter]
    st.dataframe(view, hide_index=True, use_container_width=True)

    st.subheader("기업코드 조회 구조")
    if st.button("기업코드 샘플/목록 불러오기"):
        codes = client.fetch_corp_codes()
        st.dataframe(codes.head(100), hide_index=True, use_container_width=True)


main()
