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
) -> None:
    import uvicorn

    uvicorn.run("veedor.api.main:app", host=host, port=port, reload=reload)
