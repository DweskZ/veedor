"""Release schema gate: refuse any Parquet file whose table or columns are not on the allow-list.

    python check_release_schema.py <data dir> <allow-list.json> [--with-quotes]

Reads only the Parquet footers (schemas), never the rows. The allow-list (deploy/release-columns.json)
is a reviewed, committed file: a new column cannot ship until a human adds it there. Exit 0 = ok,
1 = refused (every problem is printed), 2 = usage error. Independent of scripts/check_quotes_privacy.py,
which looks at the content of the quotes table.
"""

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    with_quotes = "--with-quotes" in argv
    if len(args) != 2 or any(a.startswith("--") and a != "--with-quotes" for a in argv):
        print(__doc__, file=sys.stderr)
        return 2
    data, allow_path = Path(args[0]), Path(args[1])
    allow = json.loads(allow_path.read_text())
    tables: dict[str, list[str]] = dict(allow["tables"])
    if with_quotes:
        tables |= allow["quotes_tables"]
    problems: list[str] = []
    seen = 0
    for path in sorted(data.rglob("*.parquet")):
        name = path.relative_to(data).with_suffix("").as_posix()
        seen += 1
        if name not in tables:
            problems.append(f"table not on the allow-list: {name}.parquet")
            continue
        columns = set(pq.read_schema(path).names)
        extra = sorted(columns - set(tables[name]))
        if extra:
            problems.append(f"{name}.parquet has columns not on the allow-list: {', '.join(extra)}")
    missing = sorted(set(tables) - {p.relative_to(data).with_suffix("").as_posix() for p in data.rglob("*.parquet")})
    for name in problems:
        print(f"REFUSED: {name}", file=sys.stderr)
    if missing:
        print(f"note: allow-listed tables not in this release: {', '.join(missing)}", file=sys.stderr)
    if problems:
        return 1
    print(f"schema gate ok: {seen} Parquet files, every table and column is on the allow-list")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
