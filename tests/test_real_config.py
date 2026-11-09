"""Static contract tests: not substitutes for running Docker/Keycloak/MCP."""
import json
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).resolve().parents[1]


def test_realm_has_business_roles_and_distinct_users():
    realm = json.loads((ROOT / "infrastructure/keycloak/acme-realm.json").read_text())
    roles = {r["name"] for r in realm["roles"]["realm"]}
    assert {"sales_user", "support_user", "admin"}.issubset(roles)
    assert len(realm["users"]) == 3
    assert len({u["id"] for u in realm["users"]}) == 3
    assert all(len(u.get("realmRoles", [])) == 1 for u in realm["users"])
    client = next(c for c in realm["clients"] if c["clientId"] == "acme-web")
    assert client["standardFlowEnabled"]
    audiences = [m["config"]["included.client.audience"] for m in client["protocolMappers"]]
    assert "acme-web" in audiences and "acme-mcp" in audiences


def test_seed_dataset_and_idempotent_inserts():
    sql = (ROOT / "database/fixtures/seed.sql").read_text()
    assert sql.count("ON CONFLICT") >= 4
    for table in ("users", "customers", "issues", "issue_updates", "user_customer_access"):
        assert f"INSERT INTO {table}" in sql
    assert "Customer reports discrepancy still present" in sql
    assert "Northstar Finance" in sql


def test_compose_includes_required_services_and_bootstraps():
    text = (ROOT / "compose.yaml").read_text()
    for name in ("postgres", "redis", "keycloak", "ollama", "model-init", "db-init", "mcp", "web"):
        assert f"  {name}:" in text
    assert "service_completed_successfully" in text
    assert "service_healthy" in text
    assert "--import-realm" in text


def test_no_mock_keycloak_auth():
    text = (ROOT / "acme_shared/security.py").read_text()
    assert "PyJWKClient" in text
    assert "RS256" in text
    assert "audience=audience" in text
    assert "issuer=issuer" in text


def test_actual_mcp_auth_and_tool_contracts():
    code = (ROOT / "mcp_server/server.py").read_text()
    for name in ("find_customer", "list_open_issues", "get_issue_history", "create_next_action"):
        assert f"def {name}(" in code
    assert "MCPServer(" in code
    assert "verify_keycloak_jwt(token, audience=\"acme-mcp\")" in code
    assert 'transport="streamable-http"' in code
