"""Graph-node contract tests with fake transports; live LangGraph/Ollama/MCP unverified."""
from types import SimpleNamespace

import pytest

from app.agent.blueprint import load_blueprint, tool_specs_for_profile
from app.agent.graph import (
    RunContext, execute_selected_tools, graph_input, reason_and_select,
    MAX_TURNS, MAX_TOOL_CALLS,
)
from tests.test_w08_blueprints import TOOL_DEFINITIONS


class FakeModel:
    def __init__(self, messages):
        self.messages = list(messages)
        self.received = []

    async def chat(self, messages, tools):
        self.received.append((messages, tools))
        return {"message": self.messages.pop(0)}


class FakeMCP:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"status": "ok", "data": {"id": "customer-123"},
                "evidence_refs": ["customers:customer-123"]}


def context(model, mcp):
    b = load_blueprint("sales_user")
    return SimpleNamespace(context=RunContext(
        blueprint=b, model=model, mcp=mcp,
        tool_definitions=tool_specs_for_profile(TOOL_DEFINITIONS, b)))


def tool_call(name, **args):
    return {"function": {"name": name, "arguments": args}}


@pytest.mark.asyncio
async def test_model_chooses_actual_tool_and_returns_verified_result():
    model = FakeModel([
        {"content": "", "tool_calls": [tool_call("find_customer", customer_name="Acme Retail")]},
        {"content": "Customer customer-123 was located.", "tool_calls": []},
    ])
    mcp = FakeMCP()
    runtime = context(model, mcp)
    state = graph_input("Find Acme Retail")
    select = await reason_and_select(state, runtime)
    assert select["status"] == "needs_tools"
    state.update({"messages": state["messages"] + select["messages"],
                  "model_turns": select["model_turns"]})
    tools = await execute_selected_tools(state, runtime)
    assert mcp.calls == [("find_customer", {"customer_name": "Acme Retail"})]
    assert tools["evidence_refs"] == ["customers:customer-123"]
    state.update({"messages": state["messages"] + tools["messages"],
                  "tool_events": tools["tool_events"]})
    finish = await reason_and_select(state, runtime)
    assert finish["status"] == "complete"
    assert "customer-123" in finish["answer"]
    assert "Authorization" not in str(model.received)


@pytest.mark.asyncio
async def test_write_tool_fails_before_any_transport_call():
    mcp = FakeMCP()
    runtime = context(FakeModel([]), mcp)
    state = graph_input("Please create an action")
    state["messages"].append({"role": "assistant", "content": "", "tool_calls": [
        tool_call("create_next_action", issue_id="irrelevant")]})
    with pytest.raises(ValueError, match="TOOL_NOT_ALLOWED"):
        await execute_selected_tools(state, runtime)
    assert not mcp.calls


@pytest.mark.asyncio
async def test_unknown_argument_fails_before_call():
    mcp = FakeMCP()
    state = graph_input("Find it")
    state["messages"].append({"role": "assistant", "tool_calls": [
        tool_call("find_customer", customer_name="A", role="admin")]})
    with pytest.raises(ValueError, match="UNEXPECTED_ARGUMENT"):
        await execute_selected_tools(state, context(FakeModel([]), mcp))
    assert not mcp.calls


@pytest.mark.asyncio
async def test_model_budget_and_missing_content_fail_closed():
    model = FakeModel([{"content": "", "tool_calls": []}])
    state = graph_input("hi")
    outcome = await reason_and_select(state, context(model, FakeMCP()))
    assert outcome["status"] == "failed"
    state["model_turns"] = MAX_TURNS
    outcome = await reason_and_select(state, context(model, FakeMCP()))
    assert outcome["status"] == "failed"


@pytest.mark.asyncio
async def test_tool_budget_failure_does_not_execute():
    mcp = FakeMCP()
    state = graph_input("Find it")
    state["tool_calls"] = MAX_TOOL_CALLS
    state["messages"].append({"role": "assistant", "tool_calls": [
        tool_call("find_customer", customer_name="A")]})
    with pytest.raises(ValueError, match="TOOL_CALL_BUDGET_EXCEEDED"):
        await execute_selected_tools(state, context(FakeModel([]), mcp))
    assert mcp.calls == []
