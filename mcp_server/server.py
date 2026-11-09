"""Actual MCP v2 Streamable-HTTP resource server, validating Keycloak bearer JWTs."""
import os
import uuid
from pydantic import AnyHttpUrl
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
from acme_shared.security import verify_keycloak_jwt
from acme_shared.policies import has_permission, principal_from_claims
from mcp_server import repository as repo

RESOURCE = os.getenv("MCP_RESOURCE_URL", "http://mcp:8001/mcp")
ISSUER = os.getenv("KEYCLOAK_ISSUER", "http://localhost:8080/realms/acme")


class KeycloakVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = verify_keycloak_jwt(token, audience="acme-mcp")
            principal_from_claims(claims)
        except Exception:
            # Fail closed on invalid tokens or temporary JWKS outage; no token details logged.
            return None
        return AccessToken(
            token=token, client_id=claims.get("azp", "unknown"),
            subject=claims["sub"], scopes=[], claims=claims,
            expires_at=claims["exp"], resource=RESOURCE,
        )


mcp = MCPServer(
    "Acme Operations Tools",
    token_verifier=KeycloakVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(ISSUER),
        resource_server_url=AnyHttpUrl(RESOURCE),
        required_scopes=[],
        # Keycloak uses the client ID 'acme-mcp' as JWT audience; verified by
        # verify_keycloak_jwt. Resource URL comparison is therefore disabled.
        validate_token_resource=False,
    ),
)


def _principal():
    verified = get_access_token()
    if verified is None or not verified.claims:
        raise PermissionError("Authentication required")
    return principal_from_claims(verified.claims)


def result(status, data=None, refs=None, error=None):
    return {"status": status, "data": data, "evidence_refs": refs or [],
            "error_code": error, "trace_id": None}


@mcp.tool()
def find_customer(customer_name: str) -> dict:
    """Find an authorised customer's profile by its name; returns evidence identifiers."""
    actor = _principal()
    if not has_permission(actor, "find_customer"):
        return result("forbidden", error="ROLE_DENIED")
    if not customer_name.strip() or len(customer_name) > 160:
        return result("validation_error", error="INVALID_CUSTOMER_NAME")
    customer = repo.find_customer(actor, customer_name.strip())
    if not customer:
        return result("not_found", error="CUSTOMER_NOT_FOUND")
    return result("ok", customer, [f"customers:{customer['id']}"])


@mcp.tool()
def list_open_issues(customer_id: str) -> dict:
    """Find currently open/investigating issues for an authorised customer."""
    actor = _principal()
    if not has_permission(actor, "list_open_issues"):
        return result("forbidden", error="ROLE_DENIED")
    try:
        cid = uuid.UUID(customer_id)
    except (ValueError, AttributeError):
        return result("validation_error", error="INVALID_CUSTOMER_ID")
    items = repo.list_open_issues(actor, cid)
    return result("ok", items, [f"issues:{i['id']}" for i in items])


@mcp.tool()
def get_issue_history(issue_id: str) -> dict:
    """Retrieve an authorised issue and its timestamped history in chronological order."""
    actor = _principal()
    if not has_permission(actor, "get_issue_history"):
        return result("forbidden", error="ROLE_DENIED")
    try:
        iid = uuid.UUID(issue_id)
    except (ValueError, AttributeError):
        return result("validation_error", error="INVALID_ISSUE_ID")
    payload = repo.get_issue_history(actor, iid)
    if not payload:
        return result("not_found", error="ISSUE_NOT_FOUND")
    refs = [f"issues:{payload['issue']['id']}"] + [f"issue_updates:{x['id']}" for x in payload['updates']]
    return result("ok", payload, refs)


@mcp.tool()
def create_next_action(issue_id: str, description: str, approval_id: str, operation_id: str) -> dict:
    """Commit a next action, admin-only, after an out-of-band human approval is recorded."""
    actor = _principal()
    if not has_permission(actor, "create_next_action"):
        return result("forbidden", error="ROLE_DENIED")
    if not description.strip() or len(description) > 1000:
        return result("validation_error", error="INVALID_DESCRIPTION")
    try:
        iid, aid, oid = uuid.UUID(issue_id), uuid.UUID(approval_id), uuid.UUID(operation_id)
    except (ValueError, AttributeError):
        return result("validation_error", error="INVALID_UUID")
    status, committed = repo.create_next_action(
        actor, issue_id=iid, description=description.strip(), approval_id=aid, operation_id=oid
    )
    return result(status, committed,
                  [f"next_actions:{committed['id']}"] if committed else [],
                  None if status == "ok" else status.upper())




@mcp.tool()
def update_issue_status(issue_id: str, new_status: str, expected_version: int,
                        note: str, approval_id: str, operation_id: str) -> dict:
    """Support/Admin: change an issue only after user confirmation and version validation."""
    actor = _principal()
    if not has_permission(actor, "update_issue_status"):
        return result("forbidden", error="ROLE_DENIED")
    if (new_status not in {"open", "investigating", "resolved", "closed"} or
            not isinstance(expected_version, int) or isinstance(expected_version, bool) or
            expected_version < 1 or not note.strip() or len(note) > 600):
        return result("validation_error", error="INVALID_STATUS_UPDATE")
    try:
        iid, aid, oid = uuid.UUID(issue_id), uuid.UUID(approval_id), uuid.UUID(operation_id)
    except (ValueError, AttributeError):
        return result("validation_error", error="INVALID_UUID")
    status, receipt = repo.update_issue_status(
        actor, issue_id=iid, new_status=new_status, expected_version=expected_version,
        note=note.strip(), approval_id=aid, operation_id=oid)
    return result(status, receipt, [f"issues:{iid}", f"issue_updates:{receipt['update_id']}"]
                  if receipt else [], None if status == "ok" else status.upper())

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001,
            stateless_http=True, json_response=True)
