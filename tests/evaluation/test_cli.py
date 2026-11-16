from __future__ import annotations

from typer.testing import CliRunner

from veedor.cli.evaluate import app
from veedor.evaluation import backtest, coverage, history, report

runner = CliRunner()


def test_commands_are_registered():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("backtest", "coverage", "report"):
        assert name in result.output


def test_report_requires_json(tmp_path):
    result = runner.invoke(app, ["report", "--eval-dir", str(tmp_path), "--out", str(tmp_path / "x.md")])
    assert result.exit_code == 1


def test_report_roundtrip(tmp_path, synthetic_dirs):
    import orjson

    bt = backtest.run_backtest(*synthetic_dirs, n_boot=100, seed=1)
    bt["history"] = [history.entry_from(bt, "synthetic run")]
    cov = coverage.run_coverage(*synthetic_dirs)
    (tmp_path / "backtest.json").write_bytes(orjson.dumps(bt, option=orjson.OPT_SERIALIZE_NUMPY))
    (tmp_path / "coverage.json").write_bytes(orjson.dumps(cov, option=orjson.OPT_SERIALIZE_NUMPY))
    out = tmp_path / "EVAL.md"
    result = runner.invoke(app, ["report", "--eval-dir", str(tmp_path), "--out", str(out)])
    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8") == report.render(
        orjson.loads((tmp_path / "backtest.json").read_bytes()),
        orjson.loads((tmp_path / "coverage.json").read_bytes()),
    )
