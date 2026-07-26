from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .container import Container, build_container
from .logging_config import configure_logging
from .schemas import AgentRequest

logger = logging.getLogger(__name__)
container: Container | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global container
    container = build_container()
    configure_logging(container.settings.log_level)
    yield
    if container:
        container.audit.close()


app = FastAPI(title="Agentic DataOps Platform", version="0.1.0", lifespan=lifespan)


def get_container() -> Container:
    if container is None:
        raise HTTPException(status_code=503, detail="Application is not initialized")
    return container


@app.get("/health")
def health() -> dict:
    current = get_container()
    return {"status": "ok", "agent_provider": current.settings.agent_provider}


@app.get("/datasets")
def datasets() -> list[dict]:
    return [item.model_dump(mode="json") for item in get_container().catalog.list_datasets()]


@app.get("/datasets/{dataset}/profile")
def profile(dataset: str) -> dict:
    try:
        return get_container().profiler.profile(dataset).model_dump(mode="json")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/agent/tasks")
def task(request: AgentRequest) -> dict:
    try:
        return get_container().agent.run(request.question, request.dataset).model_dump(mode="json")
    except Exception as exc:
        logger.exception("Agent task failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/agent/runs/{run_id}")
def run(run_id: str) -> dict:
    result = get_container().audit.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return result

