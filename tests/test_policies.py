import pytest
from acme_shared.policies import (
    Principal, principal_from_claims, effective_role, has_permission, can_read_customer
)


@pytest.mark.parametrize("role,action,allowed", [
    ("sales_user", "find_customer", True),
    ("sales_user", "create_next_action", False),
    ("sales_user", "update_issue_status", False),
    ("support_user", "update_issue_status", True),
    ("support_user", "create_next_action", False),
    ("admin", "create_next_action", True),
    ("admin", "get_issue_history", True),
    ("unknown", "find_customer", False),
])
def test_permissions(role, action, allowed):
    p = Principal("user-1", frozenset([role]))
    assert has_permission(p, action) is allowed


def test_ambiguous_roles_fail_closed():
    p = Principal("user-1", frozenset(["sales_user", "admin"]))
    assert effective_role(p) is None
    assert has_permission(p, "find_customer") is False


def test_customer_scope():
    sales = Principal("sales", frozenset(["sales_user"]))
    support = Principal("support", frozenset(["support_user"]))
    assert can_read_customer(sales, "c1", {"c1"})
    assert not can_read_customer(sales, "c2", {"c1"})
    assert can_read_customer(support, "c2", {"c1"})


def test_principal_is_from_verified_claims_only():
    p = principal_from_claims({"sub": "s-12", "preferred_username": "alex",
                               "realm_access": {"roles": ["sales_user"]}})
    assert p.sub == "s-12" and p.username == "alex"
    assert p.roles == frozenset(["sales_user"])
    with pytest.raises(ValueError):
        principal_from_claims({"realm_access": {"roles": ["admin"]}})
