from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ..policies.sql_guardrails import validate_read_only_sql
from ..schemas import QueryResult
from .catalog import DatasetCatalog, safe_identifier


class ReadOnlySQLTool:
    def __init__(self, catalog: DatasetCatalog, max_rows: int = 100, timeout_ms: int = 1_000) -> None:
        self.catalog = catalog
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms

    def execute(self, dataset: str, query: str) -> QueryResult:
        safe_query = validate_read_only_sql(query)
        path = self.catalog.resolve(dataset)
        table = safe_identifier(Path(path).stem)
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        started = time.perf_counter()
        try:
            rows = list(self.catalog.iter_rows(path))
            columns = self.catalog.describe(dataset).columns
            self._create_table(connection, table, columns, rows)
            connection.set_progress_handler(
                lambda: 1 if (time.perf_counter() - started) * 1000 > self.timeout_ms else 0,
                1_000,
            )
            cursor = connection.execute(safe_query)
            result_rows = [dict(row) for row in cursor.fetchmany(self.max_rows + 1)]
            truncated = len(result_rows) > self.max_rows
            result_rows = result_rows[: self.max_rows]
            return QueryResult(
                dataset=Path(path).name,
                query=safe_query,
                columns=[description[0] for description in cursor.description or []],
                rows=result_rows,
                row_count=len(result_rows),
                truncated=truncated,
            )
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"SQL execution failed: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _create_table(connection: sqlite3.Connection, table: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
        if not columns:
            raise ValueError("Dataset has no columns")
        quoted_columns = ", ".join(f'"{column.replace(chr(34), chr(34) * 2)}" TEXT' for column in columns)
        connection.execute(f'CREATE TABLE "{table}" ({quoted_columns})')
        placeholders = ", ".join("?" for _ in columns)
        values = [[row.get(column, "") for column in columns] for row in rows]
        connection.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', values)
        connection.commit()
