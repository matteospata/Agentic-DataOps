from __future__ import annotations

import math
from typing import Any

from ..schemas import ColumnProfile, DataProfile, DataQualityIssue
from .catalog import DatasetCatalog


class DataProfiler:
    def __init__(self, catalog: DatasetCatalog) -> None:
        self.catalog = catalog

    def profile(self, dataset: str) -> DataProfile:
        info = self.catalog.describe(dataset)
        path = self.catalog.resolve(dataset)
        rows = list(self.catalog.iter_rows(path))
        profiles: list[ColumnProfile] = []
        issues: list[DataQualityIssue] = []
        for column in info.columns:
            values = [self._string(row.get(column)) for row in rows]
            non_empty = [value for value in values if value]
            numeric = self._numeric(non_empty)
            profile = ColumnProfile(
                name=column,
                inferred_type=info.inferred_types.get(column, "unknown"),
                row_count=len(rows),
                null_count=len(rows) - len(non_empty),
                unique_count=len(set(non_empty)),
                sample_values=list(dict.fromkeys(non_empty))[:5],
                minimum=min(numeric) if numeric else None,
                maximum=max(numeric) if numeric else None,
                mean=sum(numeric) / len(numeric) if numeric else None,
            )
            profiles.append(profile)
            if profile.null_count:
                ratio = profile.null_count / max(profile.row_count, 1)
                severity = "critical" if ratio >= 0.25 else "warning"
                issues.append(DataQualityIssue(
                    severity=severity,
                    rule="not_null",
                    message=f"{ratio:.1%} of values are missing.",
                    column=column,
                ))
            if profile.inferred_type in {"integer", "number"} and numeric and any(math.isnan(item) for item in numeric):
                issues.append(DataQualityIssue(
                    severity="warning", rule="finite_numeric", message="Column contains non-finite values.", column=column
                ))
        duplicates = len(rows) - len({tuple(sorted((key, self._string(value)) for key, value in row.items())) for row in rows})
        if duplicates:
            issues.append(DataQualityIssue(
                severity="warning", rule="unique_rows", message=f"Found {duplicates} duplicate rows."
            ))
        if not rows:
            issues.append(DataQualityIssue(
                severity="critical", rule="non_empty_dataset", message="Dataset contains no rows."
            ))
        return DataProfile(dataset=info, columns=profiles, duplicate_row_count=duplicates, issues=issues)

    @staticmethod
    def _string(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _numeric(values: list[str]) -> list[float]:
        result: list[float] = []
        for value in values:
            try:
                result.append(float(value))
            except ValueError:
                return []
        return result
