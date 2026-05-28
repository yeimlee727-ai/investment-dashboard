from __future__ import annotations

from dataclasses import dataclass
import io
import math
import re
from typing import Any

import pandas as pd

PORTFOLIO_REQUIRED_COLUMNS = ("symbol", "weight_pct")
PORTFOLIO_OPTIONAL_COLUMNS = (
    "name",
    "sector",
    "country",
    "currency",
    "theme",
    "annualized_volatility_pct",
    "max_drawdown_pct",
    "total_return_pct",
    "risk_data_status",
)
CANDIDATE_REQUIRED_COLUMNS = ("symbol",)
CANDIDATE_OPTIONAL_COLUMNS = (
    "name",
    "sector",
    "country",
    "currency",
    "theme",
    "financial_metric_name",
    "financial_metric_growth_pct",
    "market_reaction_pct",
    "market_cap",
    "volume",
    "total_return_pct",
    "annualized_volatility_pct",
    "max_drawdown_pct",
    "observation_count",
    "risk_data_status",
)
PORTFOLIO_SAMPLE_ROWS = (
    {
        "symbol": "AAPL",
        "weight_pct": 24.0,
        "name": "Apple",
        "sector": "Technology",
        "country": "US",
        "currency": "USD",
        "theme": "Quality growth",
        "annualized_volatility_pct": 22.0,
        "max_drawdown_pct": -11.0,
        "total_return_pct": 12.0,
        "risk_data_status": "ok",
    },
    {
        "symbol": "JNJ",
        "weight_pct": 16.0,
        "name": "Johnson & Johnson",
        "sector": "Healthcare",
        "country": "US",
        "currency": "USD",
        "theme": "Defensive quality",
        "annualized_volatility_pct": 18.0,
        "max_drawdown_pct": -8.0,
        "total_return_pct": 4.0,
        "risk_data_status": "ok",
    },
)
CANDIDATE_SAMPLE_ROWS = (
    {
        "symbol": "MSFT",
        "name": "Microsoft",
        "sector": "Software",
        "country": "US",
        "currency": "USD",
        "theme": "Quality growth",
        "financial_metric_name": "revenue_growth",
        "financial_metric_growth_pct": 30.0,
        "market_reaction_pct": -3.0,
        "market_cap": 3000000000000,
        "volume": 25000000,
        "total_return_pct": 10.0,
        "annualized_volatility_pct": 20.0,
        "max_drawdown_pct": -10.0,
        "observation_count": 45,
        "risk_data_status": "ok",
    },
    {
        "symbol": "TSLA",
        "name": "Tesla",
        "sector": "Technology",
        "country": "US",
        "currency": "USD",
        "theme": "High beta growth",
        "financial_metric_name": "operating_income_growth",
        "financial_metric_growth_pct": -8.0,
        "market_reaction_pct": 40.0,
        "market_cap": 800000000000,
        "volume": 75000000,
        "total_return_pct": 22.0,
        "annualized_volatility_pct": 58.0,
        "max_drawdown_pct": -36.0,
        "observation_count": 45,
        "risk_data_status": "ok",
    },
)

TEXT_COLUMNS = {
    "symbol",
    "name",
    "sector",
    "country",
    "currency",
    "theme",
    "financial_metric_name",
    "risk_data_status",
}
NUMERIC_COLUMNS = {
    "weight_pct",
    "annualized_volatility_pct",
    "max_drawdown_pct",
    "total_return_pct",
    "financial_metric_growth_pct",
    "market_reaction_pct",
    "market_cap",
    "volume",
    "observation_count",
}
COLUMN_ALIASES = {
    "ticker": "symbol",
    "stock_symbol": "symbol",
    "weight": "weight_pct",
    "weight_percent": "weight_pct",
    "portfolio_weight": "weight_pct",
}


@dataclass(frozen=True)
class DecisionSupportInputConfig:
    duplicate_policy: str = "keep_first"
    default_missing_text: str = "Unknown"
    default_risk_data_status: str = "missing_price_history"


@dataclass(frozen=True)
class DecisionSupportInputValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int
    normalized_columns: list[str]


def normalize_portfolio_holdings_input(
    holdings: pd.DataFrame | list[dict[str, Any]] | None,
    config: DecisionSupportInputConfig | None = None,
) -> pd.DataFrame:
    config = config or DecisionSupportInputConfig()
    frame = _normalized_frame(holdings)
    frame = _ensure_columns(
        frame, PORTFOLIO_REQUIRED_COLUMNS + PORTFOLIO_OPTIONAL_COLUMNS
    )
    frame = _normalize_common_values(frame, config)
    if "weight_pct" in frame:
        frame["weight_pct"] = frame["weight_pct"].map(_safe_weight_pct)
    frame = _apply_risk_status(frame, config)
    return _dedupe_by_symbol(frame, config)


def normalize_candidate_universe_input(
    candidates: pd.DataFrame | list[dict[str, Any]] | None,
    config: DecisionSupportInputConfig | None = None,
) -> pd.DataFrame:
    config = config or DecisionSupportInputConfig()
    frame = _normalized_frame(candidates)
    frame = _ensure_columns(
        frame, CANDIDATE_REQUIRED_COLUMNS + CANDIDATE_OPTIONAL_COLUMNS
    )
    frame = _normalize_common_values(frame, config)
    frame = _apply_risk_status(frame, config)
    return _dedupe_by_symbol(frame, config)


def validate_portfolio_holdings_input(
    holdings: pd.DataFrame | list[dict[str, Any]] | None,
    config: DecisionSupportInputConfig | None = None,
) -> DecisionSupportInputValidationResult:
    config = config or DecisionSupportInputConfig()
    raw = _normalized_frame(holdings)
    normalized = normalize_portfolio_holdings_input(raw, config)
    errors = _missing_required_errors(raw, PORTFOLIO_REQUIRED_COLUMNS, "portfolio")
    warnings = _common_warnings(raw, normalized)
    if "weight_pct" in raw and raw["weight_pct"].map(_is_negative_number).any():
        warnings.append("Negative weight_pct values were clamped to 0.")
    return DecisionSupportInputValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        row_count=len(normalized),
        normalized_columns=list(normalized.columns),
    )


def validate_candidate_universe_input(
    candidates: pd.DataFrame | list[dict[str, Any]] | None,
    config: DecisionSupportInputConfig | None = None,
) -> DecisionSupportInputValidationResult:
    config = config or DecisionSupportInputConfig()
    raw = _normalized_frame(candidates)
    normalized = normalize_candidate_universe_input(raw, config)
    errors = _missing_required_errors(raw, CANDIDATE_REQUIRED_COLUMNS, "candidate")
    warnings = _common_warnings(raw, normalized)
    return DecisionSupportInputValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        row_count=len(normalized),
        normalized_columns=list(normalized.columns),
    )


def build_csv_input_decision_support_context(
    portfolio_holdings: pd.DataFrame | list[dict[str, Any]] | None,
    candidate_universe: pd.DataFrame | list[dict[str, Any]] | None = None,
    config: DecisionSupportInputConfig | None = None,
) -> dict[str, Any]:
    config = config or DecisionSupportInputConfig()
    normalized_holdings = normalize_portfolio_holdings_input(portfolio_holdings, config)
    normalized_candidates = normalize_candidate_universe_input(
        candidate_universe, config
    )
    portfolio_validation = validate_portfolio_holdings_input(portfolio_holdings, config)
    candidate_missing = _normalized_frame(candidate_universe).empty
    candidate_validation = (
        DecisionSupportInputValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Candidate CSV data is empty or was not provided."],
            row_count=0,
            normalized_columns=list(normalized_candidates.columns),
        )
        if candidate_missing
        else validate_candidate_universe_input(candidate_universe, config)
    )
    warnings = [
        *portfolio_validation.warnings,
        *candidate_validation.warnings,
    ]
    errors = [
        *portfolio_validation.errors,
        *candidate_validation.errors,
    ]
    validation_status = "ok"
    if errors:
        validation_status = "invalid"
    elif warnings:
        validation_status = "partial"
    return {
        "portfolio_holdings": normalized_holdings,
        "candidate_universe": normalized_candidates,
        "portfolio_validation": portfolio_validation,
        "candidate_validation": candidate_validation,
        "validation_status": validation_status,
        "validation_warnings": _dedupe_messages(warnings),
        "validation_errors": _dedupe_messages(errors),
    }


def get_portfolio_csv_schema_rows() -> list[dict[str, str]]:
    return _schema_rows(
        required_columns=PORTFOLIO_REQUIRED_COLUMNS,
        optional_columns=PORTFOLIO_OPTIONAL_COLUMNS,
        descriptions={
            "symbol": "Ticker or local symbol used to identify the position.",
            "weight_pct": "Current portfolio weight as a percentage.",
            "risk_data_status": "Use ok when supplied risk metrics are locally reviewed.",
        },
    )


def get_candidate_csv_schema_rows() -> list[dict[str, str]]:
    return _schema_rows(
        required_columns=CANDIDATE_REQUIRED_COLUMNS,
        optional_columns=CANDIDATE_OPTIONAL_COLUMNS,
        descriptions={
            "symbol": "Ticker or local symbol used to identify the candidate.",
            "financial_metric_growth_pct": "User-supplied financial metric growth percentage.",
            "market_reaction_pct": "User-supplied price or market-cap reaction percentage.",
            "risk_data_status": "Use ok when supplied risk metrics are locally reviewed.",
        },
    )


def build_sample_portfolio_csv_text() -> str:
    return _records_to_csv_text(PORTFOLIO_SAMPLE_ROWS)


def build_sample_candidate_csv_text() -> str:
    return _records_to_csv_text(CANDIDATE_SAMPLE_ROWS)


def _normalized_frame(
    value: pd.DataFrame | list[dict[str, Any]] | None,
) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
    else:
        try:
            frame = pd.DataFrame(value)
        except (TypeError, ValueError):
            frame = pd.DataFrame()
    frame.columns = [_normalize_column_name(column) for column in frame.columns]
    frame = frame.rename(
        columns={column: COLUMN_ALIASES.get(column, column) for column in frame.columns}
    )
    return frame


def _schema_rows(
    required_columns: tuple[str, ...],
    optional_columns: tuple[str, ...],
    descriptions: dict[str, str],
) -> list[dict[str, str]]:
    rows = []
    for column in [*required_columns, *optional_columns]:
        rows.append(
            {
                "column": column,
                "required": "yes" if column in required_columns else "no",
                "description": descriptions.get(column, "Optional local input field."),
            }
        )
    return rows


def _records_to_csv_text(records: tuple[dict[str, Any], ...]) -> str:
    buffer = io.StringIO()
    pd.DataFrame(list(records)).to_csv(buffer, index=False)
    return buffer.getvalue()


def _normalize_column_name(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _ensure_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    output = frame.copy()
    for column in columns:
        if column not in output:
            output[column] = None
    return output


def _normalize_common_values(
    frame: pd.DataFrame, config: DecisionSupportInputConfig
) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if column == "symbol":
            output[column] = output[column].map(_normalize_symbol)
        elif column == "risk_data_status":
            output[column] = output[column].map(
                lambda value: _safe_text(value, default="")
            )
        elif column in TEXT_COLUMNS:
            output[column] = output[column].map(
                lambda value: _safe_text(value, default=config.default_missing_text)
            )
        elif column in NUMERIC_COLUMNS:
            output[column] = output[column].map(_safe_float)
    return output


def _apply_risk_status(
    frame: pd.DataFrame, config: DecisionSupportInputConfig
) -> pd.DataFrame:
    output = frame.copy()
    if "risk_data_status" not in output:
        output["risk_data_status"] = config.default_risk_data_status
        return output
    metric_columns = [
        column
        for column in [
            "total_return_pct",
            "annualized_volatility_pct",
            "max_drawdown_pct",
        ]
        if column in output
    ]
    for index, row in output.iterrows():
        status = _safe_text(row.get("risk_data_status"), default="")
        if status:
            output.at[index, "risk_data_status"] = status
            continue
        has_metrics = any(
            _safe_float(row.get(column)) is not None for column in metric_columns
        )
        output.at[index, "risk_data_status"] = (
            "ok" if has_metrics else config.default_risk_data_status
        )
    return output


def _dedupe_by_symbol(
    frame: pd.DataFrame, config: DecisionSupportInputConfig
) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame or config.duplicate_policy != "keep_first":
        return frame.reset_index(drop=True)
    return frame.drop_duplicates(subset=["symbol"], keep="first").reset_index(drop=True)


def _missing_required_errors(
    frame: pd.DataFrame, required_columns: tuple[str, ...], label: str
) -> list[str]:
    errors = [
        f"Required {label} column missing: {column}."
        for column in required_columns
        if column not in frame
    ]
    if frame.empty:
        errors.append(f"{label.title()} CSV data is empty.")
    if "symbol" in frame:
        symbols = frame["symbol"].map(_normalize_symbol)
        if symbols.eq("").any():
            errors.append(f"{label.title()} CSV contains blank symbol values.")
    return errors


def _common_warnings(raw: pd.DataFrame, normalized: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    if "symbol" in raw:
        raw_symbols = raw["symbol"].map(_normalize_symbol)
        duplicate_count = raw_symbols[raw_symbols != ""].duplicated().sum()
        if duplicate_count:
            warnings.append("Duplicate symbols detected; keeping first record.")
    if len(raw) > len(normalized):
        warnings.append("Some duplicate rows were removed deterministically.")
    return warnings


def _dedupe_messages(messages: list[str]) -> list[str]:
    deduped = []
    for message in messages:
        if message not in deduped:
            deduped.append(message)
    return deduped


def _normalize_symbol(value: Any) -> str:
    text = _safe_text(value, default="")
    return text.upper()


def _safe_text(value: Any, default: str = "Unknown") -> str:
    if value is None:
        return default
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "inf", "-inf", "none", "<na>"}:
        return default
    return text


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _safe_weight_pct(value: Any) -> float:
    number = _safe_float(value)
    if number is None:
        return 0.0
    return max(number, 0.0)


def _is_negative_number(value: Any) -> bool:
    number = _safe_float(value)
    return number is not None and number < 0
