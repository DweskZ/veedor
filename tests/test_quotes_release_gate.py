"""The release gate over the real quotes mart (runs only when the mart is built), and the bundle refusal."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from veedor.core.settings import REPO_ROOT
from veedor.infrastructure.quotes.store import LEXICON_SCHEMA, QUOTES_SCHEMA

MARTS = REPO_ROOT / "data" / "marts"
LAKE = REPO_ROOT / "data" / "lake"
SCRIPT = REPO_ROOT / "scripts" / "check_quotes_privacy.py"
BUNDLE = REPO_ROOT / "scripts" / "build_data_bundle.sh"


def _gate_module():
    spec = importlib.util.spec_from_file_location("check_quotes_privacy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not (MARTS / "process_quotes.parquet").is_file() or not (MARTS / "quote_lexicon.parquet").is_file(),
    reason="the real quotes mart (and its lexicon) is not built",
)
def test_the_real_mart_passes_the_release_gate(capsys: pytest.CaptureFixture[str]) -> None:
    """Optional: runs when `veedor quotes build` has produced the mart. Any hit fails the test."""
    code = _gate_module().run(MARTS, LAKE)
    assert code == 0, capsys.readouterr().out


def _tiny_data(tmp_path: Path, passage: str) -> Path:
    data = tmp_path / "data"
    (data / "lake").mkdir(parents=True)
    (data / "marts").mkdir()
    row = {
        "ocid": "ocds-5wno2w-T-1", "rank": 1, "kind": "enquiry_question", "text": passage, "date": None,
        "author_kind": "oferente", "source_field": "x", "related_signal": "SINGLE_BIDDER", "similarity": 0.5,
        "truncated": False, "pair_text": None, "pair_kind": None, "pair_source_field": None,
        "pair_truncated": False,
    }  # fmt: skip
    pq.write_table(
        pa.Table.from_pylist([row], schema=QUOTES_SCHEMA), data / "marts" / "process_quotes.parquet"
    )
    lexicon = [{"token": t, "form": "lowercase"} for t in "se solicita ampliar el plazo".split()]
    pq.write_table(
        pa.Table.from_pylist(lexicon, schema=LEXICON_SCHEMA), data / "marts" / "quote_lexicon.parquet"
    )
    for name in ("processes", "tenderers", "awards"):
        pq.write_table(
            pa.table({"ocid": ["ocds-5wno2w-T-1"], "buyer_ruc": [None], "buyer_name": ["Entidad"],
                      "supplier_ruc": [None], "supplier_name": [None]}),
            data / "lake" / f"{name}.parquet",
        )  # fmt: skip
    return data


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_gate_fails_a_mart_with_a_sign_off_and_passes_a_clean_one(tmp_path: Path) -> None:
    dirty = _tiny_data(tmp_path / "dirty", "Se solicita ampliar el plazo. Atte. Zxqv Wprt")
    assert _gate_module().run(dirty / "marts", dirty / "lake") == 1
    clean = _tiny_data(tmp_path / "clean", "se solicita ampliar el plazo")
    assert _gate_module().run(clean / "marts", clean / "lake") == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_bundle_refuses_to_build_with_quotes_when_the_gate_fails(tmp_path: Path) -> None:
    data = _tiny_data(tmp_path, "Se solicita ampliar el plazo. Atte. Zxqv Wprt")
    out = tmp_path / "dist"
    env = {**os.environ, "VEEDOR_DATA_DIR": str(data), "PYTHON": sys.executable}
    result = subprocess.run(
        ["bash", str(BUNDLE), "--with-quotes", str(out)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1 and "REFUSED" in result.stderr
    assert not out.exists() or not list(out.glob("*.tar.gz"))


def test_the_bundle_script_ships_no_quotes_table_without_the_flag() -> None:
    script = BUNDLE.read_text(encoding="utf-8")
    default_tables = next(line for line in script.splitlines() if line.startswith("MART_TABLES=("))
    assert "process_quotes" not in default_tables and "quote_lexicon" not in default_tables
    assert "--with-quotes" in script and "check_quotes_privacy.py" in script
    assert script.index("check_quotes_privacy.py") < script.index('MART_TABLES+=("${QUOTE_TABLES[@]}")')
