from __future__ import annotations

import json

import typer

from .container import build_container
from .logging_config import configure_logging

app = typer.Typer(help="CLI for the Agentic DataOps platform.", no_args_is_help=True)


@app.command()
def datasets() -> None:
    """List available datasets."""
    current = build_container()
    typer.echo(json.dumps([item.model_dump(mode="json") for item in current.catalog.list_datasets()], indent=2))
    current.audit.close()


@app.command()
def profile(dataset: str = typer.Option(..., help="Dataset file name.")) -> None:
    """Profile a dataset and report data-quality issues."""
    current = build_container()
    configure_logging(current.settings.log_level)
    typer.echo(json.dumps(current.profiler.profile(dataset).model_dump(mode="json"), indent=2, ensure_ascii=False))
    current.audit.close()


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question for the agent."),
    dataset: str | None = typer.Option(None, help="Dataset file name."),
) -> None:
    """Run an auditable agent task."""
    current = build_container()
    configure_logging(current.settings.log_level)
    result = current.agent.run(question, dataset)
    typer.echo(result.answer or result.error or "No answer")
    typer.echo(f"\nRun ID: {result.run_id}")
    typer.echo(f"Status: {result.status}")
    current.audit.close()


if __name__ == "__main__":
    app()

