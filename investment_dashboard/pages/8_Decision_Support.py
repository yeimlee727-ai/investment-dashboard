from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.analysis.decision_support_demo import (
    run_csv_input_decision_support_pipeline,
    run_end_to_end_decision_support_demo,
)
from src.analysis.decision_support_inputs import (
    build_sample_candidate_csv_text,
    build_sample_portfolio_csv_text,
    get_candidate_csv_schema_rows,
    get_decision_support_sample_csv_manifest,
    get_portfolio_csv_schema_rows,
    load_decision_support_sample_csv_text,
)
from src.analysis.decision_support_package import build_decision_support_package_summary
from src.reporting.report_exporter import (
    build_decision_support_excel_bytes,
    build_decision_support_html_bytes,
    build_decision_support_report_filename,
)
from src.ui_helpers import inject_global_css, localize_columns, render_page_header


def main() -> None:
    st.set_page_config(page_title="Decision Support", layout="wide")
    inject_global_css()
    render_page_header(
        "Decision Support Preview",
        "Review demo or uploaded CSV inputs without execution, account access, or external AI calls.",
        badges=[
            ("decision-support only", "info"),
            ("no trade execution", "success"),
            ("read-only preview", "warning"),
        ],
    )
    _render_safety_notice()

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
        st.info(
            "Demo mode uses deterministic local sample data so you can inspect the review flow before uploading CSV files."
        )
        result = run_end_to_end_decision_support_demo()

    _render_result(result, mode)


def _render_result(result, mode: str) -> None:
    package = result.decision_support_package
    summary = build_decision_support_package_summary(package)

    st.divider()
    st.subheader("Decision Support summary")
    cols = st.columns(5)
    cols[0].metric("Data status", package.data_status)
    cols[1].metric("Included sections", len(summary.included_sections))
    cols[2].metric("Missing sections", len(summary.missing_sections))
    cols[3].metric("Candidates", summary.candidate_review_count)
    cols[4].metric("Action plans", summary.action_plan_count)

    if mode == "Uploaded CSV data":
        _render_validation_results(result)

    with st.expander("Safety flags", expanded=True):
        flags = pd.DataFrame(
            [
                {"flag": key, "enabled": value}
                for key, value in result.safety_flags.items()
            ]
        )
        st.dataframe(localize_columns(flags), hide_index=True, width="stretch")

    left, right = st.columns(2)
    with left:
        with st.expander("Candidate review summary", expanded=True):
            _render_records_table(
                result.candidate_scores, "No candidate records available."
            )
    with right:
        with st.expander("Portfolio fit summary", expanded=True):
            _render_records_table(
                result.portfolio_fit_results,
                "No portfolio fit records available.",
            )

    with st.expander("Action plan summary", expanded=False):
        _render_records_table(result.action_plans, "No action plan records available.")

    st.subheader("Markdown report preview")
    st.markdown(package.markdown)
    st.download_button(
        "Download markdown preview",
        data=package.markdown,
        file_name="decision_support_preview.md",
        mime="text/markdown",
    )

    _render_local_report_downloads(result)

    with st.expander("LLM-ready payload preview", expanded=mode == "Uploaded CSV data"):
        payload_text = json.dumps(
            result.llm_ready_payload, ensure_ascii=False, indent=2
        )
        st.code(
            payload_text,
            language="json",
        )
        st.download_button(
            "Download payload JSON",
            data=payload_text,
            file_name="decision_support_payload.json",
            mime="application/json",
        )

    st.subheader("Limitations / disclaimer")
    st.info(
        "Use this preview to inspect package structure, data status, safety flags, and review text. "
        "Manual validation is required before any investment decision."
    )


def _render_uploaded_csv_mode():
    st.subheader("CSV upload")
    st.caption(
        "Portfolio CSV is required. Candidate CSV is optional; missing candidate data produces a partial local review."
    )
    _render_schema_guide()

    upload_cols = st.columns(2)
    with upload_cols[0]:
        portfolio_file = st.file_uploader("Portfolio CSV", type=["csv"])
    with upload_cols[1]:
        candidate_file = st.file_uploader("Candidate CSV (optional)", type=["csv"])

    if portfolio_file is None:
        st.info("Upload a portfolio CSV to run local decision-support analysis.")
        return None
    portfolio_frame = pd.read_csv(portfolio_file)
    candidate_frame = (
        pd.read_csv(candidate_file) if candidate_file is not None else None
    )
    return run_csv_input_decision_support_pipeline(portfolio_frame, candidate_frame)


def _render_safety_notice() -> None:
    st.warning(
        "This page is read-only, decision-support only, and not financial advice. "
        "It does not connect to brokerage accounts, call external AI services, or execute orders."
    )


def _render_schema_guide() -> None:
    with st.expander("CSV schema guide and sample templates", expanded=True):
        schema_cols = st.columns(2)
        with schema_cols[0]:
            st.markdown("**Portfolio CSV**")
            st.dataframe(
                localize_columns(pd.DataFrame(get_portfolio_csv_schema_rows())),
                hide_index=True,
                width="stretch",
            )
            portfolio_template = build_sample_portfolio_csv_text()
            st.code(portfolio_template, language="csv")
            st.download_button(
                "Download portfolio sample CSV",
                data=portfolio_template,
                file_name="portfolio_sample.csv",
                mime="text/csv",
            )
        with schema_cols[1]:
            st.markdown("**Candidate CSV**")
            st.dataframe(
                localize_columns(pd.DataFrame(get_candidate_csv_schema_rows())),
                hide_index=True,
                width="stretch",
            )
            candidate_template = build_sample_candidate_csv_text()
            st.code(candidate_template, language="csv")
            st.download_button(
                "Download candidate sample CSV",
                data=candidate_template,
                file_name="candidate_sample.csv",
                mime="text/csv",
            )
        st.info(
            "Missing risk metrics are allowed, but the generated package may be marked as partial and should be reviewed manually."
        )
    _render_sample_csv_pack()


def _render_sample_csv_pack() -> None:
    with st.expander("Sample CSV Pack", expanded=False):
        st.caption(
            "These files are sample data for workflow testing only. They are not investment recommendations, and manual review is required."
        )
        manifest = get_decision_support_sample_csv_manifest()
        st.dataframe(
            localize_columns(
                pd.DataFrame(
                    [
                        {
                            "name": item["name"],
                            "kind": item["kind"],
                            "scenario": item["scenario"],
                            "description": item["description"],
                        }
                        for item in manifest
                    ]
                )
            ),
            hide_index=True,
            width="stretch",
        )
        for item in manifest:
            st.download_button(
                item["download_label"],
                data=load_decision_support_sample_csv_text(item["name"]),
                file_name=item["filename"],
                mime="text/csv",
            )


def _render_validation_results(result) -> None:
    st.subheader("Validation results")
    status_label = {
        "ok": "Ready",
        "partial": "Partial data",
        "invalid": "Missing required fields",
    }.get(result.validation_status, "Validation warning")
    st.metric("Validation status", status_label)
    if result.validation_errors:
        st.error("\n".join(result.validation_errors))
    if result.validation_warnings:
        st.warning("\n".join(result.validation_warnings))
    if not result.validation_errors and not result.validation_warnings:
        st.success("Uploaded CSV data passed local validation.")


def _render_records_table(records: list[dict], empty_message: str) -> None:
    if not records:
        st.info(empty_message)
        return
    st.dataframe(
        localize_columns(pd.DataFrame(records)), hide_index=True, width="stretch"
    )


def _render_local_report_downloads(result) -> None:
    st.subheader("Local Report Downloads")
    st.caption(
        "Download local Excel or HTML files generated from the current decision-support package."
    )
    excel_bytes = build_decision_support_excel_bytes(
        result.decision_support_package,
        positions=result.portfolio_holdings,
    )
    html_bytes = build_decision_support_html_bytes(
        result.decision_support_package,
        positions=result.portfolio_holdings,
    )
    download_cols = st.columns(2)
    with download_cols[0]:
        st.download_button(
            "Download Excel report",
            data=excel_bytes,
            file_name=build_decision_support_report_filename("xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with download_cols[1]:
        st.download_button(
            "Download HTML report",
            data=html_bytes,
            file_name=build_decision_support_report_filename("html"),
            mime="text/html",
        )


main()
