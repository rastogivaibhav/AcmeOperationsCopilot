"""Offline deterministic contract tests — NOT live model results."""
import json
from pathlib import Path

import pytest

from app.agent.tool_probe import (
    allowed_tool_definitions, validated_arguments, run_probe, score_probe, READ_TOOLS,
)
from app.agent.probe import load_cases


def tool(name, parameter):
    return {"name": name, "description": f"Read {name}", "inputSchema": {
        "type": "object", "properties": {parameter: {"type": "string"}},
        "required": [parameter]}}


MCP_CATALOG = [tool("find_customer", "customer_name"),
               tool("list_open_issues", "customer_id"),
               tool("get_issue_history", "issue_id"),
               tool("create_next_action", "issue_id")]


class FakeMCP:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return MCP_CATALOG

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "find_customer":
            if arguments["customer_name"] == "Northstar Finance":
                return {"status": "not_found", "data": None, "evidence_refs": []}
            return {"status": "ok", "data": {"id": "ac000000-0000-4000-8000-000000000001"},
                    "evidence_refs": ["customers:ac000000-0000-4000-8000-000000000001"]}
        if name == "list_open_issues":
            return {"status": "ok", "data": [{"id": "issue-001"}],
                    "evidence_refs": ["issues:issue-001"]}
        return {"status": "ok", "data": {}, "evidence_refs": ["issues:issue-001"]}


class FakeModel:
    def __init__(self, messages):
        self.messages = list(messages)
        self.received = []

    async def chat(self, messages, tools):
        self.received.append((list(messages), tools))
        return {"message": self.messages.pop(0)}


def call(name, **args):
    return {"function": {"name": name, "arguments": args}}


@pytest.mark.asyncio
async def test_real_mcp_schema_is_exposed_except_any_write():
    specs = allowed_tool_definitions(MCP_CATALOG)
    assert {x["function"]["name"] for x in specs} == READ_TOOLS
    assert all(x["function"]["parameters"].get("required") for x in specs)
    assert "create_next_action" not in json.dumps(specs)


def test_missing_mcp_tools_fail_closed():
    with pytest.raises(ValueError, match="missing required read tools"):
        allowed_tool_definitions(MCP_CATALOG[:1])


@pytest.mark.parametrize("name,args,error", [
    ("create_next_action", {"issue_id": "x"}, "TOOL_NOT_ALLOWED"),
    ("find_customer", {"customer_name": "Acme", "role": "admin"}, "UNEXPECTED_ARGUMENT"),
    ("find_customer", {}, "REQUIRED_ARGUMENT_MISSING"),
    ("find_customer", {"customer_name": 123}, "INVALID_STRING_ARGUMENT"),
    ("find_customer", "bad json", "INVALID_TOOL_ARGUMENTS"),
])
def test_reject_invalid_or_unapproved_arguments(name, args, error):
    with pytest.raises(ValueError, match=error):
        validated_arguments(name, args, allowed_tool_definitions(MCP_CATALOG))


@pytest.mark.asyncio
async def test_dynamic_chained_customer_and_issue_tool_calls():
    fake_mcp = FakeMCP()
    fake_llm = FakeModel([
        {"content": "", "tool_calls": [call("find_customer", customer_name="Acme Retail")]},
        {"content": "", "tool_calls": [call("list_open_issues", customer_id="ac000000-0000-4000-8000-000000000001")]},
        {"content": "Found the open issue issue-001", "tool_calls": []},
    ])
    result = await run_probe("Which issues are open for Acme Retail?", fake_llm, fake_mcp)
    assert result.error is None
    assert result.model_calls == 3
    assert [n for n, _ in fake_mcp.calls] == ["find_customer", "list_open_issues"]
    assert result.events[-1].evidence_refs == ["issues:issue-001"]
    assert score_probe(result, ["find_customer", "list_open_issues"])["passed"]
    assert any(x["role"] == "tool" and "customers:ac000000-0000-4000-8000-000000000001" in x["content"]
               for x in fake_llm.received[-1][0])


@pytest.mark.asyncio
async def test_model_that_does_not_call_tools_fails_required_case():
    mcp = FakeMCP()
    result = await run_probe("Show Acme Retail profile", FakeModel([{"content": "Looks fine"}]), mcp)
    assert not score_probe(result, ["find_customer"])["passed"]
    assert mcp.calls == []  # No silent fallback to hardcoded tool routing.


@pytest.mark.asyncio
async def test_unapproved_write_call_fails_without_executing():
    mcp = FakeMCP()
    model = FakeModel([{"content": "", "tool_calls": [call("create_next_action", issue_id="x")]}])
    result = await run_probe("Create an action", model, mcp)
    assert result.error == "ValueError:TOOL_NOT_ALLOWED"
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_unknown_tool_and_malformed_args_fail_closed():
    mcp = FakeMCP()
    result = await run_probe("run this", FakeModel([{"tool_calls": [call("system_shell", command="rm")]}]), mcp)
    assert result.error == "ValueError:TOOL_NOT_ALLOWED"
    assert not mcp.calls


@pytest.mark.asyncio
async def test_out_of_scope_customer_returns_not_found_not_denial_bypass():
    mcp = FakeMCP()
    model = FakeModel([{"content": "", "tool_calls": [call("find_customer", customer_name="Northstar Finance")]},
                       {"content": "I could not find an accessible matching customer"}])
    result = await run_probe("Find Northstar Finance", model, mcp)
    assert result.events[0].status == "not_found"
    assert score_probe(result, ["find_customer"], expected_status="not_found")["passed"]
    assert not score_probe(result, ["find_customer"], expected_status="ok")["passed"]


@pytest.mark.asyncio
async def test_no_tool_call_for_generic_question():
    mcp = FakeMCP()
    result = await run_probe("Explain escalation", FakeModel([{"content": "An escalation ..."}]), mcp)
    assert score_probe(result, [], expect_no_tools=True)["passed"]
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_tool_budget_prevents_extra_calls():
    mcp = FakeMCP()
    model = FakeModel([{"tool_calls": [call("find_customer", customer_name="Acme"),
                                        call("find_customer", customer_name="Acme")]}])
    result = await run_probe("get it", model, mcp, max_calls=1)
    assert result.error == "ValueError:TOOL_CALL_BUDGET_EXCEEDED"
    assert not mcp.calls


@pytest.mark.asyncio
async def test_no_tool_error_message_leaks_secrets():
    class Exploding(FakeMCP):
        async def call_tool(self, name, arguments):
            raise RuntimeError("Bearer secret-value-here")
    model = FakeModel([{"tool_calls": [call("find_customer", customer_name="Acme")]}])
    result = await run_probe("show customer", model, Exploding())
    assert result.error == "RuntimeError:EXECUTION_FAILED"
    assert "secret-value-here" not in json.dumps(result.as_dict())


def test_w07_cases_cover_three_real_tools_scope_and_noop():
    cases = load_cases(Path(__file__).resolve().parents[1] / "evals/w07_cases.json")
    assert len(cases) >= 5
    names = {tool for case in cases for tool in case["expected_tools"]}
    assert names == READ_TOOLS
    assert any(c.get("expected_status") == "not_found" for c in cases)
    assert any(c.get("expect_no_tools") for c in cases)


def test_required_evidence_prevents_false_pass_on_wrong_customer():
    from app.agent.tool_probe import ProbeResult, ToolEvent
    p = ProbeResult(answer="wrong customer", final_response_received=True,
                    events=[ToolEvent(name="find_customer", arguments={"customer_name": "Acme"},
                                      status="ok", evidence_refs=["customers:wrong"], duration_ms=1)])
    s = score_probe(p, ["find_customer"], required_evidence_refs=["customers:ac000000-0000-4000-8000-000000000001"])
    assert not s["passed"] and not s["evidence_check_passed"]
