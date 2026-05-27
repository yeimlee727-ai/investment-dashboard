from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

FIT_STRONG = "strong_fit_review"
FIT_MODERATE = "moderate_fit_review"
FIT_WEAK = "weak_fit_review"
FIT_INSUFFICIENT = "insufficient_data"

IMPACT_POSITIVE = "positive"
IMPACT_NEUTRAL = "neutral"
IMPACT_ELEVATED = "elevated"
UNKNOWN = "Unknown"


@dataclass(frozen=True)
class PortfolioFitConfig:
    max_sector_weight_pct: float = 35.0
    max_country_weight_pct: float = 60.0
    max_currency_weight_pct: float = 70.0
    high_candidate_volatility_pct: float = 45.0
    deep_candidate_drawdown_pct: float = -30.0
    diversification_weight: float = 0.35
    concentration_risk_weight: float = 0.25
    candidate_quality_weight: float = 0.25
    data_quality_weight: float = 0.15


@dataclass(frozen=True)
class PortfolioFitResult:
    symbol: str
    name: str | None
    fit_score: float
    fit_tier: str
    diversification_score: float
    concentration_risk_score: float
    candidate_quality_score: float
    data_quality_score: float
    exposure_impacts: dict[str, dict[str, Any]]
    reasons: list[str]
    cautions: list[str]
    data_status: str


@dataclass(frozen=True)
class PortfolioFitSummary:
    total_count: int
    strong_fit_review_count: int
    moderate_fit_review_count: int
    weak_fit_review_count: int
    insufficient_data_count: int
    top_fit_symbols: list[str]
    concentration_caution_symbols: list[str]
    summary_note: str


def normalize_weight_pct(value: Any) -> float:
    number = _safe_float(value)
    if number is None or number < 0:
        return 0.0
    return number


def calculate_exposure_by_field(
    holdings: pd.DataFrame | list[dict[str, Any]],
    field: str,
) -> dict[str, float]:
    frame = _input_frame(holdings)
    if frame.empty:
        return {}
    exposures: dict[str, float] = {}
    for _, row in frame.iterrows():
        key = _metadata_value(row.get(field))
        exposures[key] = exposures.get(key, 0.0) + normalize_weight_pct(
            row.get("weight_pct")
        )
    return {key: round(value, 4) for key, value in sorted(exposures.items())}


def calculate_candidate_exposure_impact(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> dict[str, dict[str, Any]]:
    config = config or PortfolioFitConfig()
    impacts = {}
    for field, limit in [
        ("sector", config.max_sector_weight_pct),
        ("country", config.max_country_weight_pct),
        ("currency", config.max_currency_weight_pct),
    ]:
        exposures = calculate_exposure_by_field(holdings, field)
        value = _metadata_value(_get(candidate, field))
        current_weight = exposures.get(value, 0.0)
        if value == UNKNOWN:
            status = IMPACT_NEUTRAL
        elif current_weight >= limit:
            status = IMPACT_ELEVATED
        elif current_weight <= limit * 0.5:
            status = IMPACT_POSITIVE
        else:
            status = IMPACT_NEUTRAL
        impacts[field] = {
            "value": value,
            "current_weight_pct": round(current_weight, 4),
            "limit_pct": limit,
            "status": status,
        }
    return impacts


def score_diversification_fit(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> float:
    impacts = calculate_candidate_exposure_impact(holdings, candidate, config)
    if any(impact["value"] == UNKNOWN for impact in impacts.values()):
        return 45.0
    score = 50.0
    for impact in impacts.values():
        if impact["status"] == IMPACT_POSITIVE:
            score += 15
        elif impact["status"] == IMPACT_ELEVATED:
            score -= 20
    return _clamp(score)


def score_concentration_risk(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> float:
    impacts = calculate_candidate_exposure_impact(holdings, candidate, config)
    score = 85.0
    for impact in impacts.values():
        if impact["value"] == UNKNOWN:
            score -= 15
        elif impact["status"] == IMPACT_ELEVATED:
            score -= 30
    return _clamp(score)


def score_candidate_quality_fit(
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> float:
    config = config or PortfolioFitConfig()
    total = _safe_float(_get(candidate, "total_score"))
    if total is None:
        return 35.0
    score = total
    volatility = _safe_float(_get(candidate, "annualized_volatility_pct"))
    drawdown = _safe_float(_get(candidate, "max_drawdown_pct"))
    if volatility is not None and volatility >= config.high_candidate_volatility_pct:
        score -= 15
    if drawdown is not None and drawdown <= config.deep_candidate_drawdown_pct:
        score -= 15
    return _clamp(score)


def score_fit_data_quality(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> float:
    required_metadata = ["symbol", "sector", "country", "currency"]
    required_scores = ["total_score", "candidate_tier", "data_status"]
    score = 100.0
    for field in required_metadata:
        if _metadata_value(_get(candidate, field)) == UNKNOWN:
            score -= 15
    for field in required_scores:
        if _optional_text(_get(candidate, field)) is None:
            score -= 15
    if _input_frame(holdings).empty:
        score -= 10
    if str(_get(candidate, "data_status", "unknown")) != "ok":
        score -= 15
    return _clamp(score)


def calculate_portfolio_fit(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidate: dict[str, Any] | pd.Series,
    config: PortfolioFitConfig | None = None,
) -> PortfolioFitResult:
    config = config or PortfolioFitConfig()
    diversification = score_diversification_fit(holdings, candidate, config)
    concentration = score_concentration_risk(holdings, candidate, config)
    quality = score_candidate_quality_fit(candidate, config)
    data_quality = score_fit_data_quality(holdings, candidate, config)
    fit_score = _clamp(
        diversification * config.diversification_weight
        + concentration * config.concentration_risk_weight
        + quality * config.candidate_quality_weight
        + data_quality * config.data_quality_weight
    )
    tier = _fit_tier(fit_score, data_quality)
    impacts = calculate_candidate_exposure_impact(holdings, candidate, config)
    reasons, cautions = _fit_messages(impacts, quality, data_quality)
    return PortfolioFitResult(
        symbol=_symbol(_get(candidate, "symbol")),
        name=_optional_text(_get(candidate, "name")),
        fit_score=round(fit_score, 4),
        fit_tier=tier,
        diversification_score=round(diversification, 4),
        concentration_risk_score=round(concentration, 4),
        candidate_quality_score=round(quality, 4),
        data_quality_score=round(data_quality, 4),
        exposure_impacts=impacts,
        reasons=reasons,
        cautions=cautions,
        data_status=str(_get(candidate, "data_status", "unknown")),
    )


def analyze_candidate_portfolio_fit(
    holdings: pd.DataFrame | list[dict[str, Any]],
    candidates: pd.DataFrame | list[dict[str, Any]],
    config: PortfolioFitConfig | None = None,
) -> list[PortfolioFitResult]:
    frame = _input_frame(candidates)
    if frame.empty:
        return []
    results = [
        calculate_portfolio_fit(holdings, row, config) for _, row in frame.iterrows()
    ]
    return sorted(results, key=lambda result: (-result.fit_score, result.symbol))


def build_portfolio_fit_summary(
    results: list[PortfolioFitResult],
) -> PortfolioFitSummary:
    result_list = list(results or [])
    concentration_symbols = [
        result.symbol
        for result in result_list
        if any(
            impact["status"] == IMPACT_ELEVATED
            for impact in result.exposure_impacts.values()
        )
    ]
    return PortfolioFitSummary(
        total_count=len(result_list),
        strong_fit_review_count=_count_tier(result_list, FIT_STRONG),
        moderate_fit_review_count=_count_tier(result_list, FIT_MODERATE),
        weak_fit_review_count=_count_tier(result_list, FIT_WEAK),
        insufficient_data_count=_count_tier(result_list, FIT_INSUFFICIENT),
        top_fit_symbols=[result.symbol for result in result_list[:5]],
        concentration_caution_symbols=concentration_symbols,
        summary_note=_summary_note(result_list, concentration_symbols),
    )


def _fit_tier(fit_score: float, data_quality: float) -> str:
    if data_quality < 45:
        return FIT_INSUFFICIENT
    if fit_score >= 70:
        return FIT_STRONG
    if fit_score >= 50:
        return FIT_MODERATE
    return FIT_WEAK


def _fit_messages(
    impacts: dict[str, dict[str, Any]],
    quality: float,
    data_quality: float,
) -> tuple[list[str], list[str]]:
    reasons = []
    cautions = []
    if any(impact["status"] == IMPACT_POSITIVE for impact in impacts.values()):
        reasons.append(
            "Candidate may improve diversification because one or more exposures are underrepresented in the current portfolio."
        )
    if quality >= 70:
        reasons.append("Candidate quality score is favorable for further review.")
    if any(impact["status"] == IMPACT_ELEVATED for impact in impacts.values()):
        cautions.append("Candidate overlaps with an already concentrated exposure.")
    if data_quality < 70:
        cautions.append(
            "Fit quality is limited because candidate metadata is incomplete."
        )
    if not reasons:
        reasons.append("Candidate fit is classified for deterministic review only.")
    cautions.append(
        "Candidate quality score is useful context, but portfolio concentration impact requires manual review."
    )
    return reasons, cautions


def _summary_note(
    results: list[PortfolioFitResult], concentration_symbols: list[str]
) -> str:
    if not results:
        return "No candidate records were available for portfolio fit analysis."
    return (
        f"Portfolio fit analysis produced {len(results)} review records, "
        f"with {len(concentration_symbols)} concentration caution records."
    )


def _count_tier(results: list[PortfolioFitResult], tier: str) -> int:
    return sum(1 for result in results if result.fit_tier == tier)


def _input_frame(value: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(value)


def _get(record: dict[str, Any] | pd.Series, key: str, default: Any = None) -> Any:
    if isinstance(record, pd.Series):
        return record.get(key, default)
    return record.get(key, default)


def _metadata_value(value: Any) -> str:
    text = _optional_text(value)
    return text if text is not None else UNKNOWN


def _symbol(value: Any) -> str:
    text = _optional_text(value)
    return text.upper() if text else ""


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in {"", "nan", "none", "<na>"} else text


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _clamp(value: Any) -> float:
    number = _safe_float(value)
    if number is None:
        return 0.0
    return max(0.0, min(100.0, number))
