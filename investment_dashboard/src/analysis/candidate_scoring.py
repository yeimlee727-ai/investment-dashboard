from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from src.analysis.investment_map import (
    QUADRANT_CHASE_RISK,
    QUADRANT_INSUFFICIENT_DATA,
    QUADRANT_JUSTIFIED_DECLINE,
    QUADRANT_JUSTIFIED_RISE,
    QUADRANT_UNDERVALUED_DISCOVERY,
)

TIER_HIGH_PRIORITY = "high_priority_review"
TIER_STANDARD = "standard_review"
TIER_CAUTION = "caution_review"
TIER_INSUFFICIENT = "insufficient_data"


@dataclass(frozen=True)
class CandidateScoringConfig:
    opportunity_weight: float = 0.40
    risk_quality_weight: float = 0.30
    momentum_quality_weight: float = 0.20
    data_quality_weight: float = 0.10
    high_volatility_pct: float = 45.0
    medium_volatility_pct: float = 25.0
    deep_drawdown_pct: float = -30.0
    medium_drawdown_pct: float = -15.0
    min_observation_count: int = 30


@dataclass(frozen=True)
class CandidateScore:
    symbol: str
    name: str | None
    market: str | None
    total_score: float
    opportunity_score: float
    risk_quality_score: float
    momentum_quality_score: float
    data_quality_score: float
    candidate_tier: str
    reasons: list[str]
    cautions: list[str]
    data_status: str


@dataclass(frozen=True)
class CandidateScoreSummary:
    total_count: int
    high_priority_review_count: int
    standard_review_count: int
    caution_review_count: int
    insufficient_data_count: int
    top_symbols: list[str]
    caution_symbols: list[str]
    summary_note: str


def clamp_score(value: Any) -> float:
    number = _safe_float(value)
    if number is None:
        return 0.0
    return max(0.0, min(100.0, number))


def score_opportunity_component(
    record: dict[str, Any] | pd.Series,
    config: CandidateScoringConfig | None = None,
) -> float:
    config = config or CandidateScoringConfig()
    quadrant = str(_get(record, "quadrant", QUADRANT_INSUFFICIENT_DATA))
    investment_map_score = clamp_score(
        _get(record, "investment_map_score", _get(record, "score", 0))
    )
    if quadrant == QUADRANT_UNDERVALUED_DISCOVERY:
        return clamp_score(70 + investment_map_score * 0.3)
    if quadrant == QUADRANT_JUSTIFIED_RISE:
        return clamp_score(55 + investment_map_score * 0.2)
    if quadrant == QUADRANT_JUSTIFIED_DECLINE:
        return 30.0
    if quadrant == QUADRANT_CHASE_RISK:
        return 15.0
    return 10.0


def score_risk_quality_component(
    record: dict[str, Any] | pd.Series,
    config: CandidateScoringConfig | None = None,
) -> float:
    config = config or CandidateScoringConfig()
    status = str(_get(record, "risk_data_status", "missing"))
    if status != "ok":
        return 30.0
    volatility = _safe_float(_get(record, "annualized_volatility_pct"))
    drawdown = _safe_float(_get(record, "max_drawdown_pct"))
    score = 80.0
    if volatility is None or drawdown is None:
        return 35.0
    if volatility >= config.high_volatility_pct:
        score -= 35
    elif volatility >= config.medium_volatility_pct:
        score -= 15
    else:
        score += 5
    if drawdown <= config.deep_drawdown_pct:
        score -= 35
    elif drawdown <= config.medium_drawdown_pct:
        score -= 15
    else:
        score += 5
    return clamp_score(score)


def score_momentum_quality_component(
    record: dict[str, Any] | pd.Series,
    config: CandidateScoringConfig | None = None,
) -> float:
    config = config or CandidateScoringConfig()
    quadrant = str(_get(record, "quadrant", QUADRANT_INSUFFICIENT_DATA))
    total_return = _safe_float(_get(record, "total_return_pct"))
    market_reaction = _safe_float(_get(record, "market_reaction_pct"))
    financial_growth = _safe_float(_get(record, "financial_metric_growth_pct"))
    if total_return is None and market_reaction is None:
        return 30.0
    score = 50.0
    if total_return is not None:
        score += max(min(total_return, 30), -30) * 0.8
    if market_reaction is not None:
        score += max(min(market_reaction, 25), -25) * 0.4
    if quadrant == QUADRANT_CHASE_RISK:
        score = min(score, 40.0)
    if financial_growth is not None and market_reaction is not None:
        if market_reaction > 20 and financial_growth < 0:
            score -= 20
    return clamp_score(score)


def score_data_quality_component(
    record: dict[str, Any] | pd.Series,
    config: CandidateScoringConfig | None = None,
) -> float:
    config = config or CandidateScoringConfig()
    status = str(_get(record, "risk_data_status", "missing"))
    observations = _safe_float(_get(record, "observation_count"))
    score = 50.0
    if status == "ok":
        score += 30
    else:
        score -= 25
    if observations is not None and observations >= config.min_observation_count:
        score += 20
    elif observations is not None and observations > 0:
        score += 5
    else:
        score -= 10
    return clamp_score(score)


def calculate_candidate_score(
    record: dict[str, Any] | pd.Series,
    config: CandidateScoringConfig | None = None,
) -> CandidateScore:
    config = config or CandidateScoringConfig()
    opportunity = score_opportunity_component(record, config)
    risk_quality = score_risk_quality_component(record, config)
    momentum = score_momentum_quality_component(record, config)
    data_quality = score_data_quality_component(record, config)
    total = clamp_score(
        opportunity * config.opportunity_weight
        + risk_quality * config.risk_quality_weight
        + momentum * config.momentum_quality_weight
        + data_quality * config.data_quality_weight
    )
    if (
        str(_get(record, "quadrant", QUADRANT_INSUFFICIENT_DATA))
        == QUADRANT_INSUFFICIENT_DATA
    ):
        total = min(total, 35.0)
    tier = _candidate_tier(record, total, data_quality)
    reasons, cautions = _reasons_and_cautions(
        record, opportunity, risk_quality, data_quality
    )
    return CandidateScore(
        symbol=_symbol(_get(record, "symbol")),
        name=_optional_text(_get(record, "name")),
        market=_optional_text(_get(record, "market")),
        total_score=round(total, 4),
        opportunity_score=round(opportunity, 4),
        risk_quality_score=round(risk_quality, 4),
        momentum_quality_score=round(momentum, 4),
        data_quality_score=round(data_quality, 4),
        candidate_tier=tier,
        reasons=reasons,
        cautions=cautions,
        data_status=str(_get(record, "risk_data_status", "unknown")),
    )


def score_candidate_records(
    records: pd.DataFrame | list[dict[str, Any]],
    config: CandidateScoringConfig | None = None,
) -> list[CandidateScore]:
    frame = _input_frame(records)
    if frame.empty:
        return []
    scores = [calculate_candidate_score(row, config) for _, row in frame.iterrows()]
    return sorted(scores, key=lambda item: (-item.total_score, item.symbol))


def build_candidate_score_summary(
    scores: list[CandidateScore],
) -> CandidateScoreSummary:
    score_list = list(scores or [])
    top_symbols = [score.symbol for score in score_list[:5]]
    caution_symbols = [
        score.symbol
        for score in score_list
        if score.candidate_tier in {TIER_CAUTION, TIER_INSUFFICIENT}
    ]
    return CandidateScoreSummary(
        total_count=len(score_list),
        high_priority_review_count=_count_tier(score_list, TIER_HIGH_PRIORITY),
        standard_review_count=_count_tier(score_list, TIER_STANDARD),
        caution_review_count=_count_tier(score_list, TIER_CAUTION),
        insufficient_data_count=_count_tier(score_list, TIER_INSUFFICIENT),
        top_symbols=top_symbols,
        caution_symbols=caution_symbols,
        summary_note=_summary_note(score_list),
    )


def _candidate_tier(
    record: dict[str, Any] | pd.Series, total: float, data_quality: float
) -> str:
    quadrant = str(_get(record, "quadrant", QUADRANT_INSUFFICIENT_DATA))
    if quadrant == QUADRANT_INSUFFICIENT_DATA or data_quality < 35:
        return TIER_INSUFFICIENT
    if quadrant == QUADRANT_CHASE_RISK or total < 45:
        return TIER_CAUTION
    if total >= 70:
        return TIER_HIGH_PRIORITY
    return TIER_STANDARD


def _reasons_and_cautions(
    record: dict[str, Any] | pd.Series,
    opportunity: float,
    risk_quality: float,
    data_quality: float,
) -> tuple[list[str], list[str]]:
    quadrant = str(_get(record, "quadrant", QUADRANT_INSUFFICIENT_DATA))
    reasons = []
    cautions = []
    if quadrant == QUADRANT_UNDERVALUED_DISCOVERY:
        reasons.append(
            "Investment Map classification suggests fundamentals improved while market reaction remains limited."
        )
    elif quadrant == QUADRANT_JUSTIFIED_RISE:
        reasons.append(
            "Investment Map classification shows both fundamentals and market reaction improved."
        )
    if opportunity >= 70:
        reasons.append("Opportunity component is elevated for further review.")
    if quadrant == QUADRANT_CHASE_RISK:
        cautions.append(
            "Market reaction appears elevated relative to the supplied fundamental growth metric."
        )
    if risk_quality < 50:
        cautions.append(
            "Risk quality is reduced due to elevated volatility or drawdown."
        )
    if data_quality < 60:
        cautions.append(
            "Data quality is limited because risk data is missing or insufficient."
        )
    if not reasons:
        reasons.append("Candidate is classified for deterministic review only.")
    cautions.append(
        "Candidate requires additional manual review before any investment decision."
    )
    return reasons, cautions


def _summary_note(scores: list[CandidateScore]) -> str:
    if not scores:
        return "No candidate records were available for scoring."
    caution_count = sum(
        1
        for score in scores
        if score.candidate_tier in {TIER_CAUTION, TIER_INSUFFICIENT}
    )
    return (
        f"Candidate scoring produced {len(scores)} review records, "
        f"including {caution_count} records with caution or limited data tiers."
    )


def _count_tier(scores: list[CandidateScore], tier: str) -> int:
    return sum(1 for score in scores if score.candidate_tier == tier)


def _input_frame(records: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    if records is None:
        return pd.DataFrame()
    if isinstance(records, pd.DataFrame):
        return records.copy()
    return pd.DataFrame(records)


def _get(record: dict[str, Any] | pd.Series, key: str, default: Any = None) -> Any:
    if isinstance(record, pd.Series):
        return record.get(key, default)
    return record.get(key, default)


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
