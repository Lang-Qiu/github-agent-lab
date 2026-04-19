"""Patch generation workflow placeholder."""

from ..agents.coder import draft_patch


def run_generate_patch(plan: str) -> str:
    return draft_patch(plan)
