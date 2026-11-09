"""File contracts: useful checks in an offline environment, not runtime verification."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_oidc_realm_pkce_and_exact_callback():
    realm = json.loads((ROOT / "infrastructure/keycloak/acme-realm.json").read_text())
    web = next(c for c in realm["clients"] if c["clientId"] == "acme-web")
    assert web["publicClient"] and web["standardFlowEnabled"]
    assert web["redirectUris"] == ["http://localhost:8000/auth/callback"]
    assert web["attributes"]["pkce.code.challenge.method"] == "S256"


def test_w06_adds_real_owner_scoped_conversations_schema():
    code = (ROOT / "database/migrations/versions/0002_conversations.py").read_text()
    assert "owner_sub" in code and "conversation_messages" in code
    repo = (ROOT / "app/conversations.py").read_text()
    assert "WHERE owner_sub=%s" in repo
    assert "WHERE id=%s AND owner_sub=%s" in repo


def test_w06_browser_uses_opaque_cookie_and_csrf_with_w08_real_agent():
    oidc = (ROOT / "app/auth/oidc.py").read_text()
    assert 'httponly=True' in oidc and 'samesite="lax"' in oidc
    assert "getdel(" in oidc and "hmac.compare_digest" in oidc
    assert '"x-csrf-token"' in oidc
    assert "id_token" in oidc and "nonce" in oidc
    main = (ROOT / "app/main.py").read_text()
    assert "async def send_agent_message" in main
    assert "execute_turn(" in main
    assert "no simulated response" not in main


def test_w06_stack_declares_redis_session_and_templates():
    compose = (ROOT / "compose.yaml").read_text()
    assert "REDIS_URL: redis://redis:6379/0" in compose
    assert "KEYCLOAK_TOKEN_URL:" in compose
    project = (ROOT / "pyproject.toml").read_text()
    assert '"redis>=' in project and '"jinja2>=' in project
    assert (ROOT / "app/templates/workspace.html").exists()
