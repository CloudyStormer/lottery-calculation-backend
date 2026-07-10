from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    database_path: Path
    cors_origins: tuple[str, ...]
    history_limit: int
    http_timeout: float


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.getenv("LOTTERY_DATABASE_PATH", "data/lottery.db")),
        cors_origins=_split_csv(os.getenv("LOTTERY_CORS_ORIGINS", "http://localhost:5173")),
        history_limit=max(300, int(os.getenv("LOTTERY_HISTORY_LIMIT", "1200"))),
        http_timeout=max(5.0, float(os.getenv("LOTTERY_HTTP_TIMEOUT", "25"))),
    )
