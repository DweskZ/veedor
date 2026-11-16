"""`veedor serve`: run the HTTP API with uvicorn."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(help="Run the API server.", invoke_without_command=True)


@app.callback()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Auto-reload on code changes (development).")] = False,
    workers: Annotated[
        int | None, typer.Option(min=1, help="Worker processes (default: VEEDOR_API_WORKERS).")
    ] = None,
) -> None:
    import uvicorn

    from veedor.core.settings import get_settings

    # `--reload` and several workers are mutually exclusive in uvicorn.
    count = 1 if reload else (workers or get_settings().api_workers)
    uvicorn.run("veedor.api.main:app", host=host, port=port, reload=reload, workers=count)
