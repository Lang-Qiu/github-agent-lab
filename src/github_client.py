"""Placeholder GitHub client for future integration."""


class GitHubClient:
    def __init__(self, token: str = "") -> None:
        self.token = token

    def read_repo_summary(self, repo_url: str) -> str:
        return (
            "GitHub read placeholder. "
            f"Future iterations will fetch metadata for {repo_url}."
        )
