"""Patch validation workflow placeholder."""

from ..agents.validator import validate_patch_content


def run_validate_patch(patch_text: str) -> str:
    return validate_patch_content(patch_text)
