"""Module entrypoint for `python -m src.main`."""

from .cli import app


def run() -> None:
    app()


if __name__ == "__main__":
    run()
