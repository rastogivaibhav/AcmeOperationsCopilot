"""Server-side role policy. Hiding a tool from an LLM is NOT authorisation."""
from dataclasses import dataclass
from typing import FrozenSet

READ_ACTIONS = frozenset({"find_customer", "list_open_issues", "get_issue_history", "propose_next_action"})
ROLE_PERMISSIONS = {
    "sales_user": READ_ACTIONS,
    "support_user": READ_ACTIONS | {"update_issue_status"},
    "admin": READ_ACTIONS | {"update_issue_status", "create_next_action"},
}
ROLE_PRIORITY = ("admin", "support_user", "sales_user")


@dataclass(frozen=True)
class Principal:
    sub: str
    roles: FrozenSet[str]
    username: str = ""


def principal_from_claims(claims: dict) -> Principal:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise ValueError("JWT missing subject")
    roles = claims.get("realm_access", {}).get("roles", [])
    return Principal(sub=sub, roles=frozenset(roles), username=claims.get("preferred_username", ""))


def effective_role(principal: Principal) -> str | None:
    # Demo policy: exactly one business role. Reject ambiguity rather than silently
    # combining privileges; production needs central role-combination policy.
    matches = [r for r in ROLE_PRIORITY if r in principal.roles]
    return matches[0] if len(matches) == 1 else None


def has_permission(principal: Principal, action: str) -> bool:
    role = effective_role(principal)
    return bool(role and action in ROLE_PERMISSIONS[role])


def can_read_customer(principal: Principal, customer_id: str, granted_customer_ids: set[str]) -> bool:
    if not has_permission(principal, "find_customer"):
        return False
    if effective_role(principal) == "sales_user":
        return customer_id in granted_customer_ids
    return True
