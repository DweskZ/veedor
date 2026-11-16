"""Regression cases rebuilt from the false rejections seen in the real-model run (see the fixture note)."""

import json
from pathlib import Path

import pytest

from veedor.domain.dossier.grounding import verify
from veedor.domain.dossier.models import EvidencePack

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "dossier" / "regression_rejections.json").read_text()
)
BASE = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "dossier" / "pack_full.json").read_text()
)


def _pack(name: str) -> EvidencePack:
    data = json.loads(json.dumps(BASE))
    for section, values in FIXTURE["pack_overrides"][name].items():
        data[section].update(values)
    return EvidencePack.model_validate(data)


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["text"][:60])
def test_regression_case(case):
    report = verify(case["text"], _pack(case["pack"]))
    assert report.passed is case["pass"], [t.model_dump() for t in report.unsupported]
