"""Regression tests for the H2 mount failure seen in the live Compose runner."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_keycloak_persists_in_postgres_not_embedded_h2():
    compose = (ROOT / "compose.yaml").read_text()
    assert "KC_DB: postgres" in compose
    assert "KC_DB_URL: jdbc:postgresql://postgres:5432/" in compose
    assert "KC_DB_SCHEMA: keycloak" in compose
    assert "kcdata:" not in compose
    assert "/opt/keycloak/data/h2" not in compose


def test_schema_bootstrap_runs_before_keycloak():
    compose = (ROOT / "compose.yaml").read_text()
    assert "python -m database.init_keycloak && alembic upgrade head" in compose
    keycloak = compose.split("  keycloak:\n", 1)[1].split("  ollama:\n", 1)[0]
    assert "db-init: {condition: service_completed_successfully}" in keycloak
    assert "KC_DB_USERNAME:" in keycloak
    assert "KC_DB_PASSWORD:" in keycloak
    script = (ROOT / "database/init_keycloak.py").read_text()
    assert "CREATE SCHEMA IF NOT EXISTS keycloak" in script
    assert "autocommit=True" in script
