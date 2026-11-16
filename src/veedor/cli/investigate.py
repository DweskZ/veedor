"""`veedor investigate ...`: run multi-agent investigations (live tools), batch them and show stored ones."""

from __future__ import annotations

import json
from typing import Annotated

import duckdb
import typer

from veedor.cli.dossier import render_text
from veedor.core.settings import REPO_ROOT, get_settings
from veedor.domain.dossier.errors import ProcessNotFoundError
from veedor.domain.investigation.models import InvestigationRecord
from veedor.domain.investigation.vocab import SOURCE_BY_TOOL
from veedor.infrastructure.investigations.store import InvestigationStore, valid_ocid
from veedor.use_cases import investigate as use_case

app = typer.Typer(help="Run multi-agent investigations with read-only tools.", no_args_is_help=True)


@app.callback()
def _telemetry() -> None:
    """Export spans and metrics when VEEDOR_OTEL_ENDPOINT is set (flushed by shutdown below)."""
    from veedor.infrastructure.telemetry import setup_telemetry

    setup_telemetry("veedor-cli")


def _flush() -> None:
    from veedor.infrastructure.telemetry import shutdown_telemetry

    shutdown_telemetry()


NoLlm = Annotated[bool, typer.Option("--no-llm", help="Deterministic policies and template; no model.")]
Offline = Annotated[
    bool,
    typer.Option(
        "--offline", help="Do not start the EcuDataMCP server; live lookups are recorded as failed."
    ),
]
SUMMARY_FILE = "investigations_run.json"


def _top_ocids(n: int) -> list[str]:
    path = get_settings().marts_dir / "process_scores.parquet"
    if not path.is_file():
        typer.echo(f"Falta {path}; ejecute primero `veedor signals build`.", err=True)
        raise typer.Exit(1)
    con = duckdb.connect(":memory:")
    rows = con.execute(
        "SELECT ocid FROM read_parquet(?) ORDER BY risk_score DESC, n_signals DESC, ocid LIMIT ?",
        [str(path), n],
    ).fetchall()
    return [r[0] for r in rows]


def _describe(record: InvestigationRecord) -> str:
    if record.dossier is None:
        mode, verified = f"retenido ({record.withheld})", False
    else:
        mode, verified = record.dossier.mode, record.dossier.grounding_report.passed
    lines = [
        f"{record.ocid}: modo={mode} verificación={verified} "
        f"especialistas={len(record.specialists)} "
        f"consultas={sum(r.n_tool_calls for r in record.specialists)} "
        f"hechos añadidos={len(record.facts_added)} llamadas al modelo={record.model_usage.calls}"
    ]
    for call in record.tool_log:
        reason = f" ({call.reason})" if call.reason else ""
        lines.append(
            f"  - {call.specialist}/{call.tool}[{call.target}]: {call.outcome}{reason} "
            f"intentos={call.attempts} {call.duration_ms:.0f} ms"
        )
    return "\n".join(lines)


def _check_ocid(ocid: str) -> None:
    if not valid_ocid(ocid):
        typer.echo(
            "Identificador de proceso no válido (vacío, demasiado largo o con caracteres de control).",
            err=True,
        )
        raise typer.Exit(2)


@app.command("run")
def run(
    ocid: str,
    no_llm: NoLlm = False,
    offline: Offline = False,
    print_: Annotated[bool, typer.Option("--print", help="Print the dossier text.")] = False,
) -> None:
    """Investigate one process and store the result in data/investigations/."""
    _check_ocid(ocid)
    with use_case.live_backend(live=not offline) as mcp:
        service = use_case.build_service(mcp=mcp, use_llm=not no_llm)
        try:
            record = service.investigate(ocid)
        except ProcessNotFoundError:
            typer.echo(f"Proceso no encontrado: {ocid}", err=True)
            raise typer.Exit(1) from None
        finally:
            service.close()
    typer.echo(_describe(record))
    _flush()
    if print_ and record.dossier is not None:
        typer.echo("")
        typer.echo(render_text(record.dossier))


@app.command("batch")
def batch(
    top: Annotated[int, typer.Option(help="Number of highest-risk processes.")] = 20,
    no_llm: NoLlm = False,
    offline: Offline = False,
    max_model_calls: Annotated[
        int, typer.Option(help="Hard cap on model calls for the whole batch.")
    ] = use_case.DEFAULT_MODEL_CALL_CAP,
) -> None:
    """Investigate the N highest-risk processes with one long-lived tool session; write counts only."""
    ocids = _top_ocids(top)
    with use_case.live_backend(live=not offline) as mcp:
        service = use_case.build_service(
            mcp=mcp, use_llm=not no_llm, model_call_cap=None if no_llm else max_model_calls
        )
        try:
            summary, _ = use_case.run_batch(
                service, ocids, on_error=lambda name: typer.echo(f"error: {name}", err=True)
            )
        finally:
            service.close()
    key = "no_llm" if no_llm else "with_llm"
    path = REPO_ROOT / "eval" / SUMMARY_FILE
    use_case.write_summary(path, {key: summary.as_dict()})
    typer.echo(json.dumps({key: summary.as_dict()}, ensure_ascii=False, indent=2))
    typer.echo(f"Resumen escrito en {path}")
    _flush()


@app.command("show")
def show(
    ocid: str,
    print_: Annotated[bool, typer.Option("--print/--no-print", help="Print the dossier text.")] = True,
) -> None:
    """Show a stored investigation (never runs one)."""
    _check_ocid(ocid)
    record = use_case.read_investigation(InvestigationStore(get_settings().data_dir / "investigations"), ocid)
    if record is None:
        typer.echo(f"No hay una investigación almacenada para {ocid}.", err=True)
        raise typer.Exit(1)
    typer.echo(_describe(record))
    typer.echo("Fuentes: " + "; ".join(sorted({SOURCE_BY_TOOL.get(c.tool, c.tool) for c in record.tool_log})))
    if print_ and record.dossier is not None:
        typer.echo("")
        typer.echo(render_text(record.dossier))
