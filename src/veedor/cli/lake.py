"""`veedor lake ...` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from veedor.core.settings import get_settings
from veedor.infrastructure.ocds.flatten import build_lake

app = typer.Typer(no_args_is_help=True)


@app.command("build")
def build(
    source: Annotated[
        Path | None, typer.Option(help="Path to the SERCOP OCDS bulk file (.jsonl.gz).")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Only process the first N releases.")] = None,
) -> None:
    """Flatten the bulk file into processes/tenderers/awards Parquet tables."""
    settings = get_settings()
    counts = build_lake(source or settings.ocds_bulk_path, settings.lake_dir, limit=limit)
    for table, rows in counts.items():
        typer.echo(f"{table}: {rows:,} rows")
