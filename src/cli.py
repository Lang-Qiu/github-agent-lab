"""Typer CLI for local experimentation workflows."""

from typing import Optional

import typer

from .workflows.apply_patch import PatchApplyError, run_apply_patch
from .workflows.analyze_repo import AnalyzeInputError, run_analyze_repo
from .workflows.discover_tasks import DiscoverTasksError, run_discover_tasks
from .workflows.generate_patch import PatchGenerationError, run_generate_patch
from .workflows.pr_draft import PRDraftError, run_pr_draft
from .workflows.run_task import RunTaskError, run_task
from .workflows.task_planning import TaskPlanningError, run_task_planning
from .workflows.validate_patch import ValidationError, run_validate_patch

app = typer.Typer(
    help="Local CLI for exploring LLM-driven GitHub contribution automation.",
    no_args_is_help=True,
)


@app.command()
def analyze(
    repo_url: str = typer.Argument(..., help="Target GitHub repository URL."),
) -> None:
    """Prepare local analysis artifacts for a target repository."""
    try:
        message = run_analyze_repo(repo_url)
    except AnalyzeInputError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command("discover-tasks")
def discover_tasks(
    repo_url: str = typer.Argument(..., help="Target GitHub repository URL."),
    use_llm: bool = typer.Option(
        False,
        "--use-llm",
        help="Use LLM-enhanced candidate discovery with fallback to rule mode.",
    ),
) -> None:
    """Discover candidate tasks from analysis summary artifacts."""
    try:
        message = run_discover_tasks(repo_url, use_llm=use_llm)
    except DiscoverTasksError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command()
def version() -> None:
    """Print the current local CLI version."""
    typer.echo("github-agent-lab 0.1.0")


@app.command()
def plan(
    task_id: str = typer.Argument(..., help="Candidate task id from candidate_tasks.json."),
    use_llm: bool = typer.Option(
        False,
        "--use-llm",
        help="Use LLM-enhanced planning with fallback to rule mode.",
    ),
) -> None:
    """Generate a minimal task_plan.json from candidate tasks."""
    try:
        message = run_task_planning(task_id, use_llm=use_llm)
    except TaskPlanningError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command()
def patch(
    task_id: str = typer.Argument(..., help="Task id from task_plan.json."),
) -> None:
    """Generate a minimal patch_preview.json from task_plan."""
    try:
        message = run_generate_patch(task_id)
    except PatchGenerationError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command()
def apply(
    task_id: str = typer.Argument(..., help="Task id from patch_preview.json."),
) -> None:
    """Apply minimal workspace edits from patch preview and task plan."""
    try:
        message = run_apply_patch(task_id)
    except PatchApplyError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command()
def validate(
    task_id: str = typer.Argument(..., help="Task id from patch_apply_result.json."),
) -> None:
    """Run minimal workspace validation for an applied patch."""
    try:
        message = run_validate_patch(task_id)
    except ValidationError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command("pr-draft")
def pr_draft(
    task_id: str = typer.Argument(..., help="Task id from existing workflow artifacts."),
    use_llm: bool = typer.Option(
        False,
        "--use-llm",
        help="Use LLM mode for markdown draft generation with fallback to rule mode.",
    ),
) -> None:
    """Generate minimal PR draft artifacts (JSON and Markdown)."""
    try:
        message = run_pr_draft(task_id, use_llm=use_llm)
    except PRDraftError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)


@app.command("run-task")
def run_task_command(
    repo_url: str = typer.Argument(..., help="Target GitHub repository URL."),
    task_id: Optional[str] = typer.Argument(
        None,
        help="Optional task id. If omitted, run-task uses the first candidate task.",
    ),
) -> None:
    """Run analyze->plan->patch->apply->validate->pr-draft end-to-end."""
    try:
        message = run_task(repo_url, task_id)
    except RunTaskError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(message)
