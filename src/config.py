"""Configuration helpers for local experiments."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    github_token: str
    llm_model: str
    llm_base_url: str


def load_settings() -> Settings:
    return Settings(
        github_token=os.getenv("GITHUB_TOKEN", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
    )
