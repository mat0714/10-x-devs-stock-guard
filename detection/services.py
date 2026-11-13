"""Public formation scoring service consumed by views and commands."""

from dataclasses import dataclass
from datetime import date

from detection.patterns import (
    Candidate,
    CandidateEvidence,
    score_double_top,
    score_head_shoulders,
)
from detection.pivots import atr, find_pivots
from marketdata.services import PriceSeries

ATR_PERIOD = 14
PIVOT_DEVIATION = 1.5
PEAK_TOLERANCE = 0.03
SHOULDER_TOLERANCE = 0.05
MIN_PIVOT_SEPARATION = 5
MIN_BARS = 60
CONFIRMED_BOOST = 0.15
GRADE_MEDIUM = 0.45
GRADE_HIGH = 0.70


@dataclass(frozen=True)
class PivotRef:
    date: date
    price: float
    kind: str


@dataclass(frozen=True)
class FormationEvidence:
    pivots: tuple[PivotRef, ...]
    neckline: float | None


@dataclass(frozen=True)
class FormationScore:
    pattern: str
    stage: str
    grade: str
    score: float
    evidence: FormationEvidence | None


_NO_SIGNAL = FormationScore(
    pattern="none",
    stage="none",
    grade="none",
    score=0.0,
    evidence=None,
)


def score_formation(price_series: PriceSeries) -> FormationScore:
    """Return the graded bearish formation for a daily-candle series.

    Never raises for a well-typed :class:`~marketdata.services.PriceSeries`;
    a series that is too short, has no usable ATR or matches no pattern maps to
    the all-``none`` result.
    """
    candles = price_series.candles
    if len(candles) < MIN_BARS:
        return _NO_SIGNAL

    atr_value = atr(candles, ATR_PERIOD)
    if atr_value is None or atr_value <= 0:
        return _NO_SIGNAL

    pivots = find_pivots(
        candles, atr_value=atr_value, deviation=PIVOT_DEVIATION
    )
    candidates = [
        candidate
        for candidate in (
            score_double_top(
                pivots,
                atr_value=atr_value,
                tolerance=PEAK_TOLERANCE,
                min_separation=MIN_PIVOT_SEPARATION,
            ),
            score_head_shoulders(
                pivots,
                atr_value=atr_value,
                tolerance=SHOULDER_TOLERANCE,
                min_separation=MIN_PIVOT_SEPARATION,
            ),
        )
        if candidate is not None
    ]
    if not candidates:
        return _NO_SIGNAL

    best = max(candidates, key=_final_score)
    final = _final_score(best)
    return FormationScore(
        pattern=best.pattern,
        stage=best.stage,
        grade=_grade(final),
        score=final,
        evidence=_to_evidence(best.evidence),
    )


def _final_score(candidate: Candidate) -> float:
    boost = CONFIRMED_BOOST if candidate.stage == "confirmed" else 0.0
    return min(1.0, candidate.sub_score + boost)


def _grade(score: float) -> str:
    if score >= GRADE_HIGH:
        return "high"
    if score >= GRADE_MEDIUM:
        return "medium"
    return "low"


def _to_evidence(evidence: CandidateEvidence) -> FormationEvidence:
    return FormationEvidence(
        pivots=tuple(
            PivotRef(date=pivot.date, price=pivot.price, kind=pivot.kind)
            for pivot in evidence.pivots
        ),
        neckline=evidence.neckline,
    )
