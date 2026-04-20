from pathlib import Path


def test_publish_documentation_and_env_examples_exist() -> None:
    readme_text = Path("README.md").read_text(encoding="utf-8")
    env_example_text = Path(".env.example").read_text(encoding="utf-8")

    assert "publish" in readme_text.lower()
    assert "python -m src.main publish" in readme_text
    assert "draft PR" in readme_text
    assert "main/master" in readme_text
    assert "pytest -q" in readme_text
    assert "integration" in readme_text.lower()

    assert "GITHUB_TOKEN" in env_example_text
    assert "GITHUB_PUBLISH_BASE_BRANCH" in env_example_text
    assert "GITHUB_PUBLISH_REMOTE" in env_example_text
