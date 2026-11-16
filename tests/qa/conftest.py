# ruff: noqa: E501
"""Fixtures of the question-answering tests (helpers live in `qa_support`)."""

from __future__ import annotations

import pytest
from qa_support import load_pack, make_context, with_investigation

from veedor.domain.dossier.models import EvidencePack
from veedor.use_cases.ask import ProcessContext


@pytest.fixture
def full_pack() -> EvidencePack:
    return with_investigation(load_pack("pack_full"))


@pytest.fixture
def natural_pack() -> EvidencePack:
    return load_pack("pack_natural")


@pytest.fixture
def full_context(full_pack) -> ProcessContext:
    return make_context(full_pack)
