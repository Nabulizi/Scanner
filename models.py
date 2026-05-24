"""
models.py — Shared result shapes for the scanner.

TypedDicts keep the plain-dict style while documenting the contracts between
indicator calculation, scoring, and CLI display.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PriceData(TypedDict):
    close: float
    bb_lower: float
    bb_upper: float
    bb_mid: float
    stoch_k: float
    stoch_d: float


class DataQuality(TypedDict, total=False):
    valid: bool
    bars_returned: int
    required_bars: int
    warnings: list[str]


class SignalResult(TypedDict, total=False):
    near_lower_bb: bool
    near_upper_bb: bool
    bb_expanding: bool
    stoch_oversold_cross: bool
    stoch_overbought_cross: bool
    stoch_mid_range: bool
    fvg: dict[str, Any]
    direction: str
    price_data: PriceData
    earnings_soon: bool
    data_quality: DataQuality


class CheckReason(TypedDict):
    key: str
    passed: bool
    label: str


class ScoreResult(TypedDict, total=False):
    ticker: str
    score: int
    total: int
    verdict: str
    direction: str
    checks: dict[str, bool]
    fvg_detail: dict[str, Any]
    core_count: int
    has_fvg: bool
    has_bb: bool
    has_stoch: bool
    hard_blockers: list[str]
    blocker_reasons: list[str]
    check_reasons: list[CheckReason]
    score_sections: dict[str, str]
