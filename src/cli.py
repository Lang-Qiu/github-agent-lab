"""Typer CLI for local experimentation workflows."""

import typer

from .workflows.analyze_repo import AnalyzeInputError, run_analyze_repo

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
