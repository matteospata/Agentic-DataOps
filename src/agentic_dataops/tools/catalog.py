from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterator

from ..schemas import DatasetInfo

SUPPORTED_FORMATS = {".csv", ".json", ".jsonl"}


def safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]", "_", value.strip().lower())
    identifier = re.sub(r"_+", "_", identifier).strip("_") or "dataset"
    if identifier[0].isdigit():
        identifier = f"dataset_{identifier}"
    return identifier


class DatasetCatalog:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def list_datasets(self) -> list[DatasetInfo]:
        return [self.describe(path.name) for path in sorted(self.data_dir.rglob("*")) if self._supported(path)]

    def resolve(self, dataset: str) -> Path:
        requested = Path(dataset)
        candidates = [requested, self.data_dir / requested, self.data_dir / requested.name]
        for candidate in candidates:
            if candidate.is_file() and self._supported(candidate):
                return candidate.resolve()
        matches = [path for path in self.data_dir.rglob(requested.name) if self._supported(path)]
        if len(matches) == 1:
            return matches[0].resolve()
        if not matches:
            raise FileNotFoundError(f"Dataset not found: {dataset}")
        raise ValueError(f"Dataset name is ambiguous: {dataset}")

    def describe(self, dataset: str) -> DatasetInfo:
        path = self.resolve(dataset)
        rows = list(self.iter_rows(path))
        columns = list(rows[0].keys()) if rows else self._columns_from_file(path)
        inferred_types = {
            column: self._infer_type([str(row.get(column, "")) for row in rows]) for column in columns
        }
        return DatasetInfo(
            name=path.name,
            path=str(path),
            format=path.suffix.lower().lstrip("."),
            row_count=len(rows),
            columns=columns,
            inferred_types=inferred_types,
            size_bytes=path.stat().st_size,
        )

    def iter_rows(self, path: str | Path) -> Iterator[dict[str, Any]]:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            with file_path.open(newline="", encoding="utf-8") as handle:
                yield from csv.DictReader(handle)
            return
        if suffix == ".jsonl":
            for line in file_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    if isinstance(record, dict):
                        yield record
            return
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if isinstance(record, dict):
                yield record

    @staticmethod
    def _supported(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS

    def _columns_from_file(self, path: Path) -> list[str]:
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle).fieldnames or [])
        return []

    @staticmethod
    def _infer_type(values: list[str]) -> str:
        non_empty = [value.strip() for value in values if value is not None and value.strip()]
        if not non_empty:
            return "unknown"
        lowered = {value.lower() for value in non_empty}
        if lowered <= {"true", "false", "0", "1"}:
            return "boolean"
        try:
            numbers = [float(value) for value in non_empty]
        except ValueError:
            numbers = []
        if numbers:
            return "integer" if all(number.is_integer() for number in numbers) else "number"
        if all(len(value) >= 8 and value[4] == "-" and value[7] == "-" for value in non_empty):
            return "date"
        return "string"

