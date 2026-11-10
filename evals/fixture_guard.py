"""Reproducible, read-only business fixture checksum for the live evaluator.

Only counts and SHA-256 digests are persisted, never business contents,
bearer tokens, or database credentials. Run W10 mutations AFTER --verify.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

BASELINE = Path("evals/results/fixture-baseline.json")
QUERIES = {
    "customers": "SELECT id,name,status,account_owner_sub FROM customers ORDER BY id",
    "issues": "SELECT id,customer_id,status,priority,version,sla_due_at FROM issues ORDER BY id",
    "issue_updates": "SELECT id,issue_id,author_sub,content,created_at FROM issue_updates ORDER BY id",
    "next_actions": "SELECT id,issue_id,description,created_by_sub FROM next_actions ORDER BY id",
}
EXPECTED_COUNTS = {"customers": 3, "issues": 9, "issue_updates": 8, "next_actions": 0}


def fingerprint() -> dict:
    import psycopg
    from psycopg.rows import dict_row
    payload = {}
    counts = {}
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        with db.cursor() as cursor:
            for name, sql in QUERIES.items():
                cursor.execute(sql)
                rows = cursor.fetchall()
                counts[name] = len(rows)
                payload[name] = rows
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return {"sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "counts": counts, "mode": "read_only_business_fixture"}


def check(mode: str, baseline: Path = BASELINE) -> bool:
    result = fingerprint()
    if mode == "capture":
        if result["counts"] != EXPECTED_COUNTS:
            print("FIXTURE_BASELINE_NOT_CLEAN", result["counts"])
            return False
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(result, indent=2) + "\n")
        print("FIXTURE_BASELINE_CAPTURED", result["sha256"][:16])
        return True
    if not baseline.is_file():
        print("FIXTURE_BASELINE_MISSING")
        return False
    prior = json.loads(baseline.read_text())
    matches = (result["sha256"] == prior.get("sha256") and
               result["counts"] == prior.get("counts"))
    print("FIXTURE_INTEGRITY_PASS" if matches else "FIXTURE_INTEGRITY_FAILED",
          result["sha256"][:16])
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--capture", action="store_true")
    selection.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    return 0 if check("capture" if args.capture else "verify") else 1


if __name__ == "__main__":
    raise SystemExit(main())
