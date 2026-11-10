"""Current-turn evidence binding, recovery and non-bypass contracts."""
import json
from types import SimpleNamespace

import pytest

from app.agent.evidence import (bind_customer_argument, bind_issue_argument,
                                verified_customer_ids, trusted_identifiers,
                                redact_unverified_identifiers)
from app.agent.graph import graph_input, execute_selected_tools, reason_and_select, RunContext
from app.agent.blueprint import load_blueprint, agent_specs_for_profile
from evals.w13_scoring import score_agent_case
from evals.run_w13 import INPUT
from tests.test_w08_blueprints import TOOL_DEFINITIONS
from app.agent.tool_probe import run_probe, score_probe

CUSTOMER = "ac000000-0000-4000-8000-000000000001"
ISSUE = "ab000000-0000-4000-8000-000000000001"
OWNER = "cafe0000-0000-4000-8000-000000000001"


def tool_message(tool, data, status="ok"):
    return {"role": "tool", "tool_name": tool, "content": json.dumps({
        "status": status, "data": data, "evidence_refs": []})}


def history():
    return tool_message("get_issue_history", {"issue": {"id": ISSUE, "version": 1}, "updates": []})


def customer():
    return tool_message("find_customer", {"id": CUSTOMER, "account_owner_sub": OWNER})


def call(name, **kwargs):
    return {"function": {"name": name, "arguments": kwargs}}


class FakeMCP:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return TOOL_DEFINITIONS

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "find_customer":
            return {"status": "ok", "data": {
                "id": CUSTOMER, "name": "Acme Retail", "account_owner_sub": OWNER},
                "evidence_refs": ["customers:" + CUSTOMER]}
        if name == "list_open_issues":
            return {"status": "ok", "data": [{"id": ISSUE, "customer_id": CUSTOMER}],
                    "evidence_refs": ["issues:" + ISSUE]}
        if name == "get_issue_history":
            return {"status": "ok", "data": {"issue": {"id": ISSUE, "version": 1},
                                             "updates": []},
                    "evidence_refs": ["issues:" + ISSUE]}
        return {"status": "not_found", "data": None, "evidence_refs": []}


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)

    async def chat(self, messages, tools):
        return {"message": self.replies.pop(0)}


def runtime(role, mcp, model=None):
    bp = load_blueprint(role)
    return SimpleNamespace(context=RunContext(bp, model, mcp,
        agent_specs_for_profile(TOOL_DEFINITIONS, bp)))


def test_placeholder_binds_only_from_unique_authorized_current_turn_lookup():
    messages = [{"role": "user", "content": "Acme Retail"}, customer()]
    args, status = bind_customer_argument("list_open_issues", {"customer_id": "<customer_id>"}, messages)
    assert args["customer_id"] == CUSTOMER
    assert status == "BOUND_FROM_VERIFIED_CUSTOMER_LOOKUP"
    assert bind_customer_argument("list_open_issues", {"customer_id": "?"}, [{"role": "user", "content": "X"}])[1] == "VERIFIED_CUSTOMER_ID_REQUIRED"
    assert verified_customer_ids([customer(), {"role": "user", "content": "new turn"}]) == set()
    many = messages + [tool_message("find_customer", {"id": "ac000000-0000-4000-8000-000000000002"})]
    assert bind_customer_argument("list_open_issues", {"customer_id": "?"}, many)[1] == "VERIFIED_CUSTOMER_ID_REQUIRED"


def test_valid_other_id_cannot_be_rewritten_to_verifed_customer():
    other = "ac000000-0000-4000-8000-000000000099"
    args, status = bind_customer_argument("list_open_issues", {"customer_id": other}, [customer()])
    assert args["customer_id"] == other
    assert status == "CUSTOMER_ID_MISMATCH_WITH_VERIFIED_LOOKUP"


def test_proposal_issue_reference_requires_successful_history():
    args, status = bind_issue_argument("request_next_action", {
        "issue_id": "<issue_id>", "description": "Contact"}, [history()])
    assert args["issue_id"] == ISSUE and status == "BOUND_FROM_VERIFIED_ISSUE_HISTORY"
    assert bind_issue_argument("request_next_action", {"issue_id": "bad"}, [])[1] == "VERIFIED_ISSUE_ID_REQUIRED"


def test_grounded_owner_identifier_allowed_unverified_identifier_redacted():
    msgs = [{"role": "user", "content": "Acme Retail"}, customer()]
    assert OWNER in trusted_identifiers(msgs)
    bad = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    answer, changed = redact_unverified_identifiers("Owner " + OWNER + " and " + bad, msgs)
    assert changed and OWNER in answer and bad not in answer
    case = json.loads(INPUT.read_text())["cases"][0]
    result = {"status": "complete", "answer": "Acme Retail owner " + OWNER,
              "tool_events": [{"name": "find_customer", "status": "ok"}],
              "grounded_identifiers": list(trusted_identifiers(msgs)),
              "evidence_refs": ["customers:" + CUSTOMER], "proposed_actions": []}
    assert score_agent_case(case, result)["passed"]
    result["grounded_identifiers"] = []
    assert not score_agent_case(case, result)["passed"]


@pytest.mark.asyncio
async def test_graph_binds_placeholder_into_authenticated_call():
    mcp = FakeMCP()
    state = graph_input("Which issues are open for Acme Retail?")
    state["messages"] += [customer(), {"role": "assistant", "tool_calls": [
        call("list_open_issues", customer_id="<customer_id>")]}]
    result = await execute_selected_tools(state, runtime("sales_user", mcp))
    assert mcp.calls == [("list_open_issues", {"customer_id": CUSTOMER})]
    assert result["tool_events"][0]["argument_resolution"] == "BOUND_FROM_VERIFIED_CUSTOMER_LOOKUP"
    assert "issues:" + ISSUE in result["evidence_refs"]


@pytest.mark.asyncio
async def test_graph_refuses_different_customer_without_transport_call():
    mcp = FakeMCP()
    state = graph_input("Acme Retail")
    state["messages"] += [customer(), {"role": "assistant", "tool_calls": [
        call("list_open_issues", customer_id="ac000000-0000-4000-8000-000000000099")]}]
    result = await execute_selected_tools(state, runtime("sales_user", mcp))
    assert not mcp.calls
    assert result["tool_events"][0]["error_code"] == "CUSTOMER_ID_MISMATCH_WITH_VERIFIED_LOOKUP"


@pytest.mark.asyncio
async def test_invalid_skill_id_is_feedback_not_crash():
    mcp = FakeMCP()
    state = graph_input("Assess risk")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("customer_escalation_summary", customer_id="not-a-uuid")]})
    result = await execute_selected_tools(state, runtime("sales_user", mcp))
    assert not mcp.calls and result["tool_events"][0]["status"] == "validation_error"


@pytest.mark.asyncio
async def test_admin_proposal_issue_id_bound_to_authorized_history():
    mcp = FakeMCP()
    state = graph_input("Suggest next step")
    state["messages"] += [history(), {"role": "assistant", "tool_calls": [
        call("request_next_action", issue_id="bad", description="Contact owner")]}]
    result = await execute_selected_tools(state, runtime("admin", mcp))
    assert not mcp.calls
    assert result["tool_events"][0]["status"] == "approval_required"
    assert result["proposed_actions"][0]["issue_id"] == ISSUE


@pytest.mark.asyncio
async def test_sales_write_request_rejected_before_model_and_mcp():
    mcp = FakeMCP()
    result = await reason_and_select(
        graph_input("Please close issue " + ISSUE + " right now."),
        runtime("sales_user", mcp, FakeModel([])))
    assert result["status"] == "complete" and "read-only" in result["answer"]
    assert not mcp.calls


@pytest.mark.asyncio
async def test_w07_model_selected_tool_binds_placeholder():
    model = FakeModel([
        {"content": "", "tool_calls": [call("find_customer", customer_name="Acme Retail")]},
        {"content": "", "tool_calls": [call("list_open_issues", customer_id="<customer_id>")]},
        {"content": "Open issue " + ISSUE},
    ])
    mcp = FakeMCP()
    result = await run_probe("Show open issues for Acme Retail", model, mcp)
    assert result.error is None
    assert [name for name, _ in mcp.calls] == ["find_customer", "list_open_issues"]
    assert mcp.calls[1][1]["customer_id"] == CUSTOMER
    assert score_probe(result, ["find_customer", "list_open_issues"],
                       required_evidence_refs=["issues:" + ISSUE])["passed"]


@pytest.mark.asyncio
async def test_missing_required_skill_argument_is_model_feedback_not_exception():
    mcp = FakeMCP()
    state = graph_input("Assess risk")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("customer_escalation_summary")]})
    outcome = await execute_selected_tools(state, runtime("sales_user", mcp))
    assert outcome["tool_events"][0]["error_code"] == "REQUIRED_ARGUMENT_MISSING"
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_same_batch_find_then_issues_uses_first_authenticated_tool_result():
    mcp = FakeMCP()
    state = graph_input("Find Acme Retail and show its open issues")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("find_customer", customer_name="Acme Retail"),
        call("list_open_issues", customer_id="<customer_id>")]})
    result = await execute_selected_tools(state, runtime("sales_user", mcp))
    assert [name for name, _ in mcp.calls] == ["find_customer", "list_open_issues"]
    assert mcp.calls[1][1]["customer_id"] == CUSTOMER
    assert "issues:" + ISSUE in result["evidence_refs"]


def test_ollama_model_residency_and_generation_budget(monkeypatch):
    from app.agent.transports import OllamaChat
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    model = OllamaChat()
    assert model.keep_alive == "30m"
    assert model.num_predict == 512
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "2000")
    with pytest.raises(ValueError, match="OLLAMA_NUM_PREDICT_INVALID"):
        OllamaChat()
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "512")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "invalid")
    with pytest.raises(ValueError, match="OLLAMA_KEEP_ALIVE_INVALID"):
        OllamaChat()
