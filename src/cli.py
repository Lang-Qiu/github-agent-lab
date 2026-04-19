"""Typer CLI for local experimentation workflows."""

import typer

from .workflows.apply_patch import PatchApplyError, run_apply_patch
from .workflows.analyze_repo import AnalyzeInputError, run_analyze_repo
from .workflows.generate_patch import PatchGenerationError, run_generate_patch
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


@app.command()
def version() -> None:
    """Print the current local CLI version."""
    typer.echo("github-agent-lab 0.1.0")


@app.command()
def plan(
    task_id: str = typer.Argument(..., help="Candidate task id from candidate_tasks.json."),
) -> None:
    """Generate a minimal task_plan.json from candidate tasks."""
    try:
        message = run_task_planning(task_id)
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
