from pathlib import Path

from agentic_dataops.agents.orchestrator import AgentService, HeuristicAgent
from agentic_dataops.storage.audit import AuditStore
from agentic_dataops.tools.catalog import DatasetCatalog
from agentic_dataops.tools.knowledge import KnowledgeBase
from agentic_dataops.tools.profiling import DataProfiler
from agentic_dataops.tools.sql import ReadOnlySQLTool


def test_heuristic_agent_runs_auditable_workflow(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    kb = tmp_path / "knowledge_base"
    raw.mkdir()
    kb.mkdir()
    (raw / "sales.csv").write_text("region,revenue\nNorth,10\nSouth,5\n", encoding="utf-8")
    (kb / "rules.md").write_text("# Quality rules\nRevenue should be non-negative and non-null.", encoding="utf-8")
    catalog = DatasetCatalog(raw)
    audit = AuditStore(tmp_path / "audit.db")
    service = AgentService(catalog, DataProfiler(catalog), ReadOnlySQLTool(catalog), KnowledgeBase(kb), audit, HeuristicAgent())
    run = service.run("Compare revenue by region and check data quality.", "sales.csv")
    assert run.status == "completed"
    assert run.query_result is not None
    assert run.query_result.rows[0]["dimension"] == "North"
    assert len(run.tool_calls) >= 3
    assert audit.get_run(run.run_id)["status"] == "completed"
    audit.close()

