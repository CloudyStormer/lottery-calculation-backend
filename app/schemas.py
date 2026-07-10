from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DrawRecord(BaseModel):
    game_id: str
    issue: str
    draw_date: date
    numbers: list[int]
    source_url: str


class GenerateRequest(BaseModel):
    play_id: str | None = None
    refresh: bool = False


class CandidateLane(BaseModel):
    key: str
    label: str
    color: str
    numbers: list[str]


class Candidate(BaseModel):
    rank: int
    score_index: float = Field(ge=0, le=100)
    lanes: list[CandidateLane]


class Diagnostic(BaseModel):
    sample_size: int
    latest_issue: str
    latest_date: date
    windows: list[int]
    uniformity_p_value: float
    entropy_ratio: float
    mean_abs_lag1_correlation: float
    validated_signal: bool
    validation_note: str


class GenerateResponse(BaseModel):
    game_id: str
    game_name: str
    play_id: str
    play_name: str
    theoretical_odds: str
    generated_at: datetime
    candidates: list[Candidate]
    diagnostic: Diagnostic
    data_source: str
    official_url: str
    methodology: list[str]
    warnings: list[str]


class SyncResponse(BaseModel):
    game_id: str
    fetched: int
    stored: int
    latest_issue: str | None
    synced_at: datetime
