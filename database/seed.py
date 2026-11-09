"""Repeatable fictional demo fixtures; safe to rerun (never overwrites user changes)."""
import os
from pathlib import Path
import psycopg


def main() -> None:
    fixture = Path(__file__).parent / "fixtures" / "seed.sql"
    statements = fixture.read_text(encoding="utf-8").split("-- statement")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=False) as db:
        with db.cursor() as cursor:
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
    print("Seed records initialised (idempotent).")


if __name__ == "__main__":
    main()
