from pathlib import Path

from agentic_dataops.tools.catalog import DatasetCatalog
from agentic_dataops.tools.profiling import DataProfiler
from agentic_dataops.tools.sql import ReadOnlySQLTool


def test_catalog_and_profiler_detect_missing_values(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    (data_dir / "sales.csv").write_text("region,revenue\nNorth,10\nSouth,\n", encoding="utf-8")
    catalog = DatasetCatalog(data_dir)
    profile = DataProfiler(catalog).profile("sales.csv")
    assert profile.dataset.row_count == 2
    assert any(issue.column == "revenue" for issue in profile.issues)


def test_sql_tool_returns_aggregates(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    (data_dir / "sales.csv").write_text("region,revenue\nNorth,10\nNorth,20\nSouth,5\n", encoding="utf-8")
    result = ReadOnlySQLTool(DatasetCatalog(data_dir)).execute(
        "sales.csv",
        'SELECT region, SUM(CAST("revenue" AS REAL)) AS total FROM "sales" GROUP BY region ORDER BY total DESC',
    )
    assert result.rows[0]["region"] == "North"
    assert result.rows[0]["total"] == 30.0

