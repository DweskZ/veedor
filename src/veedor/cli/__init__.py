"""Command-line entry point. Each area registers its own sub-application.

Sub-apps live in sibling modules (`veedor/cli/<area>.py`) exposing a Typer `app`.
A missing module is skipped so partially built checkouts still run.
"""

from __future__ import annotations

from importlib import import_module

import typer

app = typer.Typer(help="Veedor: open risk radar for public procurement in Ecuador.", no_args_is_help=True)

_SUB_APPS = {
    "lake": "Build the Parquet lake from the SERCOP bulk file.",
    "registries": "Download and load SRI / Supercias registries.",
    "signals": "Compute indicators, scores and marts.",
    "dossier": "Build evidence dossiers.",
    "investigate": "Run multi-agent investigations with read-only tools.",
    "vectors": "Build and query the vector index of processes.",
    "evaluate": "Run the evaluation harness.",
    "serve": "Run the API server.",
}

for _name, _help in _SUB_APPS.items():
    try:
        _module = import_module(f"veedor.cli.{_name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"veedor.cli.{_name}":
            raise
        continue
    app.add_typer(_module.app, name=_name, help=_help)
