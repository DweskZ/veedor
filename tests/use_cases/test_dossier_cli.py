import json

from typer.testing import CliRunner

from veedor.agents.investigator.tracing import Trace, TraceWriter
from veedor.cli.dossier import app
from veedor.core.settings import get_settings


def test_traces_summary_reads_the_trace_file(tmp_path, monkeypatch):
    monkeypatch.setenv("VEEDOR_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        assert "Sin trazas" in runner.invoke(app, ["traces", "--summary"]).output
        writer = TraceWriter(tmp_path / "traces")
        for ms in (10.0, 20.0, 30.0):
            writer.write(
                Trace(ocid="o", started_at="2026-01-01T00:00:00Z", total_ms=ms, final_mode="template")
            )
        out = runner.invoke(app, ["traces", "--summary"]).output
        summary = json.loads(out)
        assert (
            summary["runs"] == 3 and summary["latency_ms_p50"] == 20.0 and summary["latency_ms_p95"] == 30.0
        )
    finally:
        get_settings.cache_clear()


def test_dossier_build_rejects_a_malformed_identifier_in_one_line():
    from veedor.cli.dossier import app as dossier_app
    from veedor.cli.investigate import app as investigate_app

    runner = CliRunner()
    commands = ((dossier_app, ["build"]), (investigate_app, ["run"]), (investigate_app, ["show"]))
    for command_app, args in commands:
        for bad in ("", "a\tb", "x" * 301, " padded "):
            result = runner.invoke(command_app, [*args, bad])
            assert result.exit_code == 2, (args, bad)
            assert "Traceback" not in result.output and "│" not in result.output
            assert "Identificador de proceso no válido" in result.output
            assert len(result.output.strip().splitlines()) == 1
