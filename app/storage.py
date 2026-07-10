from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import DrawRecord


class DrawStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS draws (
                    game_id TEXT NOT NULL,
                    issue TEXT NOT NULL,
                    draw_date TEXT NOT NULL,
                    numbers TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (game_id, issue)
                );
                CREATE INDEX IF NOT EXISTS idx_draws_game_date
                    ON draws (game_id, draw_date, issue);
                CREATE TABLE IF NOT EXISTS sync_state (
                    game_id TEXT PRIMARY KEY,
                    synced_at TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    latest_issue TEXT
                );
                """
            )

    def upsert_many(self, records: list[DrawRecord]) -> int:
        if not records:
            return 0
        fetched_at = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                record.game_id,
                record.issue,
                record.draw_date.isoformat(),
                json.dumps(record.numbers, separators=(",", ":")),
                record.source_url,
                fetched_at,
            )
            for record in records
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO draws (
                    game_id, issue, draw_date, numbers, source_url, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id, issue) DO UPDATE SET
                    draw_date=excluded.draw_date,
                    numbers=excluded.numbers,
                    source_url=excluded.source_url,
                    fetched_at=excluded.fetched_at
                """,
                rows,
            )
            latest = max(records, key=lambda item: (item.draw_date, item.issue))
            count = connection.execute(
                "SELECT COUNT(*) FROM draws WHERE game_id = ?", (latest.game_id,)
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO sync_state (game_id, synced_at, record_count, latest_issue)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    synced_at=excluded.synced_at,
                    record_count=excluded.record_count,
                    latest_issue=excluded.latest_issue
                """,
                (latest.game_id, fetched_at, count, latest.issue),
            )
        return len(rows)

    def get_draws(self, game_id: str, limit: int | None = None) -> list[DrawRecord]:
        query = """
            SELECT game_id, issue, draw_date, numbers, source_url
            FROM draws WHERE game_id = ?
            ORDER BY draw_date DESC, issue DESC
        """
        params: list[object] = [game_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        records = [
            DrawRecord(
                game_id=row["game_id"],
                issue=row["issue"],
                draw_date=row["draw_date"],
                numbers=json.loads(row["numbers"]),
                source_url=row["source_url"],
            )
            for row in rows
        ]
        records.reverse()
        return records

    def count(self, game_id: str) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM draws WHERE game_id = ?", (game_id,)
                ).fetchone()[0]
            )

    def statuses(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT game_id, synced_at, record_count, latest_issue
                FROM sync_state ORDER BY game_id
                """
            ).fetchall()
        return [dict(row) for row in rows]
