"""W08 deterministic policy/blueprint tests. No external AI service mocked as successful."""
from dataclasses import replace

import pytest

from app.agent.blueprint import load_blueprint, tool_specs_for_profile
from app.agent.graph import graph_input, route_after_model


TOOL_DEFINITIONS = [
    {"name": name, "description": name, "inputSchema": {
        "type": "object", "properties": {param: {"type": "string"}}, "required": [param]}}
    for name, param in [("find_customer", "customer_name"),
                        ("list_open_issues", "customer_id"),
                        ("get_issue_history", "issue_id"),
                        ("create_next_action", "issue_id")]
]


def test_three_role_profiles_share_enterprise_standards():
    roles = [load_blueprint(role) for role in ("sales_user", "support_user", "admin")]
    assert len({p.persona for p in roles}) == 3
    assert len({p.principles for p in roles}) == 1
    assert all("read-only" in p.system_prompt for p in roles)
    assert all("0.4.0" in p.version for p in roles)


def test_unknown_role_rejected():
    with pytest.raises(ValueError, match="UNKNOWN_AGENT_ROLE"):
        load_blueprint("superuser")


def test_blueprint_cannot_escalate_write_permissions():
    original = load_blueprint("admin")
    modified = replace(original, tools=original.tools | {"create_next_action"})
    # Even a forged, immutable Blueprint object cannot broaden tool visibility.
    assert "create_next_action" not in original.tools
    with pytest.raises(ValueError, match="BLUEPRINT_TOOL_ESCALATION"):
        tool_specs_for_profile(TOOL_DEFINITIONS, modified)


def test_mcp_catalog_does_not_leak_write_tool_to_model():
    for role in ("sales_user", "support_user", "admin"):
        result = tool_specs_for_profile(TOOL_DEFINITIONS, load_blueprint(role))
        names = {x["function"]["name"] for x in result}
        assert names == {"find_customer", "list_open_issues", "get_issue_history"}
        assert "create_next_action" not in names


def test_missing_real_mcp_tool_fails_closed():
    with pytest.raises(ValueError, match="MCP_PROFILE_TOOL_MISSING"):
        tool_specs_for_profile(TOOL_DEFINITIONS[:1], load_blueprint("sales_user"))


def test_input_and_routing_limits():
    assert graph_input("hello")["messages"] == [{"role": "user", "content": "hello"}]
    assert route_after_model({"status": "needs_tools"}) == "tools"
    assert route_after_model({"status": "complete"}) == "end"
    with pytest.raises(ValueError):
        graph_input(" ")
    with pytest.raises(ValueError):
        graph_input("x" * 2001)
