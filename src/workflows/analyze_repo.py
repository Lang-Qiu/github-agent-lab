"""Repository analysis workflow placeholder."""

from ..agents.planner import build_plan
from ..agents.scout import scout_repo


def run_analyze_repo(repo_url: str) -> str:
    findings = scout_repo(repo_url)
    plan = build_plan(findings)
    return (
        "Analyze placeholder complete.\n"
        f"repo_url: {repo_url}\n"
        f"findings: {findings}\n"
        f"next_plan: {plan}\n"
        "Future iterations will connect real GitHub reads and LLM calls."
    )
