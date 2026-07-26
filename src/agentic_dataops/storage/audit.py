from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class AuditStore:
    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
              run_id TEXT PRIMARY KEY, question TEXT NOT NULL, dataset TEXT,
              status TEXT NOT NULL, answer TEXT, payload_json TEXT,
              started_at TEXT NOT NULL, finished_at TEXT, error TEXT
            );
            CREATE TABLE IF NOT EXISTS tool_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
              tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL,
              result_json TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def create_run(self, run: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO agent_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run["run_id"], run["question"], run.get("dataset"), run["status"], None, None,
             run["started_at"], None, None),
        )
        self.connection.commit()

    def record_tool_event(self, run_id: str, tool_name: str, arguments: dict[str, Any], result: Any, status: str) -> None:
        from datetime import datetime, timezone

        self.connection.execute(
            "INSERT INTO tool_events(run_id, tool_name, arguments_json, result_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, tool_name, json.dumps(arguments), json.dumps(result), status, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def finish_run(self, run: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE agent_runs SET status=?, answer=?, payload_json=?, finished_at=?, error=? WHERE run_id=?",
            (run["status"], run.get("answer"), json.dumps(run), run.get("finished_at"), run.get("error"), run["run_id"]),
        )
        self.connection.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT payload_json FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row["payload_json"]) if row and row["payload_json"] else None

    def close(self) -> None:
        self.connection.close()

