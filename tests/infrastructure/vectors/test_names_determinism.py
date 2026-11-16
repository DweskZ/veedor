from __future__ import annotations

import itertools

from veedor.infrastructure.vectors.names import buyer_names_from, most_frequent_names


class FakeLake:
    def __init__(self, rows):
        self.rows = rows

    def has_table(self, name):
        return True

    def fetch(self, sql, params, tables=()):
        assert "any_value" not in sql
        return list(self.rows)


ROWS = [
    {"buyer_ruc": "1760001040001", "buyer_name": "GAD MUNICIPAL B", "n": 5},
    {"buyer_ruc": "1760001040001", "buyer_name": "GAD MUNICIPAL A", "n": 2},
    {"buyer_ruc": "1760001040001", "buyer_name": "GAD MUNICIPAL C", "n": 5},
    {"buyer_ruc": "1760002000001", "buyer_name": "HOSPITAL X", "n": 1},
]


def test_most_frequent_name_wins_and_ties_take_the_smallest_name():
    names = most_frequent_names(ROWS)
    assert names == {"1760001040001": "GAD MUNICIPAL B", "1760002000001": "HOSPITAL X"}


def test_the_answer_does_not_depend_on_row_order():
    answers = {tuple(sorted(most_frequent_names(list(p)).items())) for p in itertools.permutations(ROWS)}
    assert len(answers) == 1


def test_buyer_names_from_uses_the_deterministic_rule():
    lake = FakeLake(list(reversed(ROWS)))
    assert buyer_names_from(lake, ["1760001040001", "1760002000001"])["1760001040001"] == "GAD MUNICIPAL B"
