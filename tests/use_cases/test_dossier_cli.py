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
