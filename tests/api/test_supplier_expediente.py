"""Regression: the Supercias file number arrives as an integer from the registry table."""

from veedor.schemas.suppliers import SuperciasFacts


def test_expediente_integer_is_exposed_as_text() -> None:
    payload = {"ruc": "0990000000001", "expediente": 147192, "legal_name": "ACME S.A."}
    facts = SuperciasFacts.model_validate(payload)
    assert facts.expediente == "147192"


def test_expediente_missing_stays_none() -> None:
    assert SuperciasFacts.model_validate({"ruc": "0990000000001"}).expediente is None
