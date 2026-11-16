import json
from pathlib import Path

import pytest

from veedor.domain.dossier.models import EvidencePack

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "dossier"


def load_pack(name: str) -> EvidencePack:
    return EvidencePack.model_validate(json.loads((FIXTURES / f"{name}.json").read_text()))


@pytest.fixture
def full_pack() -> EvidencePack:
    return load_pack("pack_full")


@pytest.fixture
def minimal_pack() -> EvidencePack:
    return load_pack("pack_minimal")


@pytest.fixture
def natural_pack() -> EvidencePack:
    return load_pack("pack_natural")
