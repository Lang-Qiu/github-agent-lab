"""Typer CLI for local experimentation workflows."""

import typer

from .workflows.analyze_repo import run_analyze_repo

app = typer.Typer(
    help="Local CLI for exploring LLM-driven GitHub contribution automation.",
    no_args_is_help=True,
)


@app.command()
def analyze(
    repo_url: str = typer.Argument(..., help="Target GitHub repository URL."),
) -> None:
    """Prepare local analysis artifacts for a target repository."""
    message = run_analyze_repo(repo_url)
    typer.echo(message)


@app.command()
def version() -> None:
    """Print the current local CLI version."""
    typer.echo("github-agent-lab 0.1.0")
