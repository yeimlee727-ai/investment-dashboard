from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis.decision_support_demo import run_end_to_end_decision_support_demo
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
        "This preview uses deterministic mock data. It is not financial advice and does not execute orders."
    )

    demo = run_end_to_end_decision_support_demo()
    package = demo.decision_support_package
    summary = build_decision_support_package_summary(package)

    cols = st.columns(5)
    cols[0].metric("Data status", package.data_status)
    cols[1].metric("Included sections", len(summary.included_sections))
    cols[2].metric("Missing sections", len(summary.missing_sections))
    cols[3].metric("Candidates", summary.candidate_review_count)
    cols[4].metric("Action plans", summary.action_plan_count)

    st.subheader("Safety flags")
    flags = pd.DataFrame(
        [{"flag": key, "enabled": value} for key, value in package.safety_flags.items()]
    )
    st.dataframe(localize_columns(flags), hide_index=True, width="stretch")

    st.subheader("Candidate review summary")
    st.dataframe(
        localize_columns(pd.DataFrame(demo.candidate_scores)),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Portfolio fit summary")
    st.dataframe(
        localize_columns(pd.DataFrame(demo.portfolio_fit_results)),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Action plan summary")
    st.dataframe(
        localize_columns(pd.DataFrame(demo.action_plans)),
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


main()
