#!/usr/bin/env python3
"""Basic validation for the generated Merchant supplemental feed."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

REQUIRED = {
    "id",
    "title",
    "brand",
    "identifier_exists",
    "condition",
    "link",
    "price",
    "availability",
}


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "feeds" / "merchant_supplemental_feed.csv"
    if not path.exists():
        print(f"MISSING {path}", file=sys.stderr)
        return 1

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    missing_cols = REQUIRED - fieldnames
    if missing_cols:
        print(f"FAIL missing columns: {sorted(missing_cols)}", file=sys.stderr)
        return 1
    if not rows:
        print("FAIL empty feed", file=sys.stderr)
        return 1

    bad_ids = [r["id"] for r in rows if not r["id"].startswith("shopify_GB_")]
    empty_titles = sum(1 for r in rows if not r["title"].strip())
    labels = Counter(r["custom_label_0"] for r in rows)
    identifiers = Counter(r["identifier_exists"] for r in rows)

    print(f"rows={len(rows)}")
    print(f"labels={dict(labels)}")
    print(f"identifier_exists={dict(identifiers)}")
    print(f"bad_ids={len(bad_ids)} empty_titles={empty_titles}")

    if bad_ids or empty_titles:
        return 1
    if identifiers.get("no", 0) < 1:
        print("FAIL expected identifier_exists=no rows for custom catalogue", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
