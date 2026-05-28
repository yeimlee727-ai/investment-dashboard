from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.analysis.decision_support_demo import (
    run_csv_input_decision_support_pipeline,
    run_end_to_end_decision_support_demo,
)
from src.analysis.decision_support_package import build_decision_support_package_summary
from src.ui_helpers import inject_global_css, localize_columns, render_page_header


def main() -> None:
    st.set_page_config(page_title="Decision Support", layout="wide")
    inject_global_css()
    render_page_header(
        "Decision Support Preview",
        "Mock inputs only. Review package output without execution, account access, or external AI calls.",
        badges=[
            ("decision-support only", "info"),
            ("no trade execution", "success"),
            ("mock preview", "warning"),
        ],
    )
    st.warning(
        "This preview is read-only. It is not financial advice and does not execute orders."
    )

    mode = st.radio(
        "Input mode",
        ["Demo sample data", "Uploaded CSV data"],
        horizontal=True,
    )
    if mode == "Uploaded CSV data":
        result = _render_uploaded_csv_mode()
        if result is None:
            return
    else:
        result = run_end_to_end_decision_support_demo()

    package = result.decision_support_package
    summary = build_decision_support_package_summary(package)

    cols = st.columns(5)
    cols[0].metric("Data status", package.data_status)
    cols[1].metric("Included sections", len(summary.included_sections))
    cols[2].metric("Missing sections", len(summary.missing_sections))
    cols[3].metric("Candidates", summary.candidate_review_count)
    cols[4].metric("Action plans", summary.action_plan_count)

    st.subheader("Safety flags")
    flags = pd.DataFrame(
        [{"flag": key, "enabled": value} for key, value in result.safety_flags.items()]
    )
    st.dataframe(localize_columns(flags), hide_index=True, width="stretch")

    if mode == "Uploaded CSV data":
        st.subheader("Validation warnings")
        if result.validation_errors:
            st.error("\n".join(result.validation_errors))
        if result.validation_warnings:
            st.warning("\n".join(result.validation_warnings))
        if not result.validation_errors and not result.validation_warnings:
            st.success("Uploaded CSV data passed local validation.")

    st.subheader("Candidate review summary")
    st.dataframe(
        localize_columns(pd.DataFrame(result.candidate_scores)),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Portfolio fit summary")
    st.dataframe(
        localize_columns(pd.DataFrame(result.portfolio_fit_results)),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Action plan summary")
    st.dataframe(
        localize_columns(pd.DataFrame(result.action_plans)),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Package summary")
    st.markdown(package.markdown)

    st.subheader("Manual review note")
    st.info(
        "Use this preview to inspect package structure, data status, safety flags, and review text. "
        "Manual validation is required before any investment decision."
    )

    if mode == "Uploaded CSV data":
        st.subheader("LLM-ready payload preview")
        st.code(
            json.dumps(result.llm_ready_payload, ensure_ascii=False, indent=2),
            language="json",
        )


def _render_uploaded_csv_mode():
    with st.expander("Expected CSV columns", expanded=False):
        st.markdown("""
            **Portfolio CSV required columns:** `symbol`, `weight_pct`

            **Portfolio CSV optional columns:** `name`, `sector`, `country`, `currency`, `theme`,
            `annualized_volatility_pct`, `max_drawdown_pct`, `total_return_pct`, `risk_data_status`

            **Candidate CSV required columns:** `symbol`

            **Candidate CSV optional columns:** `name`, `sector`, `country`, `currency`, `theme`,
            `financial_metric_name`, `financial_metric_growth_pct`, `market_reaction_pct`,
            `market_cap`, `volume`, `total_return_pct`, `annualized_volatility_pct`,
            `max_drawdown_pct`, `observation_count`, `risk_data_status`
            """)
    portfolio_file = st.file_uploader("Portfolio CSV", type=["csv"])
    candidate_file = st.file_uploader("Candidate CSV (optional)", type=["csv"])
    if portfolio_file is None:
        st.info("Upload a portfolio CSV to run local decision-support analysis.")
        return None
    portfolio_frame = pd.read_csv(portfolio_file)
    candidate_frame = (
        pd.read_csv(candidate_file) if candidate_file is not None else None
    )
    return run_csv_input_decision_support_pipeline(portfolio_frame, candidate_frame)


main()
