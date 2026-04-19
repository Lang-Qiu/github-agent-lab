"""Placeholder LLM client for future integration."""


class LLMClient:
    def __init__(self, model: str, base_url: str = "") -> None:
        self.model = model
        self.base_url = base_url

    def generate(self, prompt: str) -> str:
        return (
            "LLM placeholder response. "
            "Future iterations will call a real provider. "
            f"model={self.model}; prompt_chars={len(prompt)}"
        )
