from __future__ import annotations

from dataclasses import dataclass

from .agents.orchestrator import AgentService, build_agent_provider
from .config import Settings, get_settings
from .storage.audit import AuditStore
from .tools.catalog import DatasetCatalog
from .tools.knowledge import KnowledgeBase
from .tools.profiling import DataProfiler
from .tools.sql import ReadOnlySQLTool


@dataclass
class Container:
    settings: Settings
    catalog: DatasetCatalog
    profiler: DataProfiler
    sql_tool: ReadOnlySQLTool
    knowledge_base: KnowledgeBase
    audit: AuditStore
    agent: AgentService


def build_container(settings: Settings | None = None) -> Container:
    current = settings or get_settings()
    current.ensure_directories()
    catalog = DatasetCatalog(current.data_dir / "raw")
    profiler = DataProfiler(catalog)
    sql_tool = ReadOnlySQLTool(catalog, current.max_result_rows, current.sql_timeout_ms)
    knowledge_base = KnowledgeBase(current.knowledge_base_dir)
    audit = AuditStore(current.database_path)
    agent = AgentService(
        catalog=catalog,
        profiler=profiler,
        sql_tool=sql_tool,
        knowledge_base=knowledge_base,
        audit=audit,
        provider=build_agent_provider(current.agent_provider, current.openai_api_key, current.llm_model, current.max_tool_calls),
    )
    return Container(current, catalog, profiler, sql_tool, knowledge_base, audit, agent)

