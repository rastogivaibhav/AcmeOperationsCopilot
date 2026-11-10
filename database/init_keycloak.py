"""Idempotent schema bootstrap for Keycloak on the shared Postgres service.

The local assessment stack uses one PostgreSQL container and separates identity
from business tables by schema. Production deployments should also use
independent database roles and credentials.
"""

import os

import psycopg


def main() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS keycloak")
    print("Keycloak PostgreSQL schema ready.")


if __name__ == "__main__":
    main()
