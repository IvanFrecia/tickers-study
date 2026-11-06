"""Core package for the unified ticker forecasting pipeline.

Keep package import lightweight so dashboard and utility modules can import
`src.*` helpers without pulling the full training stack into memory.
"""


def main() -> None:
    """Lazy CLI entrypoint wrapper used by lightweight importers."""
    from .cli import main as cli_main

    cli_main()
