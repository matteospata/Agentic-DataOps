from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..schemas import AgentRun, DataProfile, KnowledgeResult, QueryResult
from ..storage.audit import AuditStore
from ..tools.catalog import DatasetCatalog, safe_identifier
from ..tools.knowledge import KnowledgeBase
from ..tools.profiling import DataProfiler
from ..tools.sql import ReadOnlySQLTool

logger = logging.getLogger(__name__)


class AgentProvider(ABC):
    @abstractmethod
    def answer(self, service: "AgentService", run: AgentRun) -> str:
        raise NotImplementedError


class AgentService:
    def __init__(
        self,
        catalog: DatasetCatalog,
        profiler: DataProfiler,
        sql_tool: ReadOnlySQLTool,
        knowledge_base: KnowledgeBase,
        audit: AuditStore,
        provider: AgentProvider,
    ) -> None:
        self.catalog = catalog
        self.profiler = profiler
        self.sql_tool = sql_tool
        self.knowledge_base = knowledge_base
        self.audit = audit
        self.provider = provider

    def run(self, question: str, dataset: str | None = None) -> AgentRun:
        run = AgentRun(run_id=uuid.uuid4().hex, question=question, dataset=dataset)
        self.audit.create_run(run.model_dump(mode="json"))
        try:
            run.answer = self.provider.answer(self, run)
            run.status = "completed"
        except Exception as exc:
            logger.exception("Agent run failed")
            run.status = "failed"
            run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        self.audit.finish_run(run.model_dump(mode="json"))
        return run

    def choose_dataset(self, requested: str | None) -> str:
        if requested:
            return self.catalog.resolve(requested).name
        datasets = self.catalog.list_datasets()
        if not datasets:
            raise FileNotFoundError("No supported datasets are available")
        if len(datasets) > 1:
            raise ValueError("A dataset must be specified when multiple datasets are available")
        return datasets[0].name

    def profile(self, run: AgentRun, dataset: str) -> DataProfile:
        profile = self.profiler.profile(dataset)
        run.dataset = dataset
        run.profile = profile
        self._record(run, "profile_dataset", {"dataset": dataset}, profile.model_dump(mode="json"))
        return profile

    def execute_sql(self, run: AgentRun, dataset: str, query: str) -> QueryResult:
        result = self.sql_tool.execute(dataset, query)
        run.query_result = result
        self._record(run, "run_readonly_sql", {"dataset": dataset, "query": query}, result.model_dump(mode="json"))
        return result

    def search_knowledge(self, run: AgentRun, query: str) -> list[KnowledgeResult]:
        results = self.knowledge_base.search(query)
        run.knowledge = results
        self._record(run, "search_knowledge_base", {"query": query}, [item.model_dump(mode="json") for item in results])
        return results

    def list_datasets(self, run: AgentRun) -> list[dict[str, Any]]:
        results = [item.model_dump(mode="json") for item in self.catalog.list_datasets()]
        self._record(run, "list_datasets", {}, results)
        return results

    def _record(self, run: AgentRun, name: str, arguments: dict[str, Any], result: Any) -> None:
        run.tool_calls.append({"tool": name, "arguments": arguments, "result": result})
        self.audit.record_tool_event(run.run_id, name, arguments, result, "completed")


class HeuristicAgent(AgentProvider):
    """Deterministic local agent: useful for demos, tests, and offline development."""

    def answer(self, service: AgentService, run: AgentRun) -> str:
        dataset = service.choose_dataset(run.dataset)
        profile = service.profile(run, dataset)
        question = run.question.lower()
        knowledge = service.search_knowledge(run, run.question)
        query_result: QueryResult | None = None
        if self._needs_query(question):
            query = self._build_query(question, dataset, profile.dataset.columns)
            query_result = service.execute_sql(run, dataset, query)
        return self._compose_answer(run, profile, query_result, knowledge)

    @staticmethod
    def _needs_query(question: str) -> bool:
        return any(term in question for term in (
            "compare", "region", "revenue", "sales", "average", "mean", "total", "sum", "highest", "lowest", "trend"
        ))

    @staticmethod
    def _build_query(question: str, dataset: str, columns: list[str]) -> str:
        table = safe_identifier(Path(dataset).stem)
        lower_columns = {column.lower(): column for column in columns}
        numeric = next((lower_columns[name] for name in ("revenue", "sales", "amount", "value") if name in lower_columns), None)
        dimension = next((lower_columns[name] for name in ("region", "category", "segment") if name in lower_columns), None)
        if "trend" in question and "date" in lower_columns and numeric:
            return f'SELECT "{lower_columns["date"]}" AS date, SUM(CAST("{numeric}" AS REAL)) AS total_value FROM "{table}" GROUP BY date ORDER BY date LIMIT 100'
        if dimension and numeric:
            aggregate = "AVG" if any(term in question for term in ("average", "mean")) else "SUM"
            metric = safe_identifier(numeric)
            return f'SELECT "{dimension}" AS dimension, {aggregate}(CAST("{numeric}" AS REAL)) AS {aggregate.lower()}_{metric}, COUNT(*) AS records FROM "{table}" GROUP BY dimension ORDER BY {aggregate.lower()}_{metric} DESC LIMIT 20'
        return f'SELECT * FROM "{table}" LIMIT 20'

    @staticmethod
    def _compose_answer(run: AgentRun, profile: DataProfile, query: QueryResult | None, knowledge: list[KnowledgeResult]) -> str:
        issues = profile.issues
        lines = [
            f"Dataset `{profile.dataset.name}` contains {profile.dataset.row_count} rows and {len(profile.dataset.columns)} columns.",
            f"Detected data-quality issues: {len(issues)}.",
        ]
        for issue in issues[:5]:
            location = f" in `{issue.column}`" if issue.column else ""
            lines.append(f"- {issue.severity.upper()}{location}: {issue.message}")
        if query and query.rows:
            lines.append(f"\nRead-only SQL result ({query.row_count} rows):")
            lines.extend(f"- {row}" for row in query.rows[:10])
        elif query:
            lines.append("\nThe read-only query returned no rows.")
        if knowledge:
            lines.append("\nRelevant knowledge sources:")
            lines.extend(f"- [S{index}] {item.title} ({item.source})" for index, item in enumerate(knowledge, 1))
        lines.append("\nThis run is auditable: every tool call and its result were recorded.")
        return "\n".join(lines)


class OpenAIAgent(AgentProvider):
    """Responses API tool-calling adapter; the tools remain local and policy-controlled."""

    def __init__(self, api_key: str, model: str, max_tool_calls: int = 8) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the 'llm' extra to use the OpenAI agent provider") from exc
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tool_calls = max_tool_calls

    def answer(self, service: AgentService, run: AgentRun) -> str:
        tools = self._tool_definitions()
        instructions = (
            "You are a safe DataOps agent. Use the available tools to inspect datasets, profile data, "
            "run read-only SQL, and search the knowledge base. Never write or mutate data. "
            "Explain findings, data-quality risks, and cite knowledge sources as [S1], [S2]. "
            "If a dataset is required, use the requested dataset or list available datasets first."
        )
        inputs: list[Any] = [{"role": "user", "content": run.question}]
        if run.dataset:
            inputs[0]["content"] += f"\nRequested dataset: {run.dataset}"
        for _ in range(self.max_tool_calls):
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=inputs,
                tools=tools,
            )
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                return response.output_text.strip()
            inputs.extend(response.output)
            for call in calls:
                arguments = json.loads(call.arguments or "{}")
                result = self._dispatch(service, run, call.name, arguments)
                inputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
        raise RuntimeError("Agent reached the maximum number of tool calls")

    def _dispatch(self, service: AgentService, run: AgentRun, name: str, arguments: dict[str, Any]) -> Any:
        if name == "list_datasets":
            return service.list_datasets(run)
        if name == "profile_dataset":
            return service.profile(run, arguments["dataset"]).model_dump(mode="json")
        if name == "run_readonly_sql":
            return service.execute_sql(run, arguments["dataset"], arguments["query"]).model_dump(mode="json")
        if name == "search_knowledge_base":
            return [item.model_dump(mode="json") for item in service.search_knowledge(run, arguments["query"])]
        raise ValueError(f"Unknown tool requested by model: {name}")

    @staticmethod
    def _tool_definitions() -> list[dict[str, Any]]:
        return [
            {"type": "function", "name": "list_datasets", "description": "List available datasets.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"type": "function", "name": "profile_dataset", "description": "Profile a dataset and return data-quality issues.", "parameters": {"type": "object", "properties": {"dataset": {"type": "string"}}, "required": ["dataset"], "additionalProperties": False}},
            {"type": "function", "name": "run_readonly_sql", "description": "Execute one safe SELECT or WITH query against a dataset.", "parameters": {"type": "object", "properties": {"dataset": {"type": "string"}, "query": {"type": "string"}}, "required": ["dataset", "query"], "additionalProperties": False}},
            {"type": "function", "name": "search_knowledge_base", "description": "Search data contracts and quality documentation.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
        ]


def build_agent_provider(provider: str, api_key: str | None, model: str, max_tool_calls: int) -> AgentProvider:
    if provider == "heuristic":
        return HeuristicAgent()
    if provider == "openai":
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai agent provider")
        return OpenAIAgent(api_key, model, max_tool_calls)
    raise ValueError(f"Unknown agent provider: {provider}")
