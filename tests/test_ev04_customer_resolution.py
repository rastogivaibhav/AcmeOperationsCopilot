"""EV04 regression: repair missing customer locator without bypassing MCP scope.

The model still selects the Skill. Only explicit current-turn user names can
fill missing inputs, and all customer and issue reads are authenticated MCP calls.
"""
from __future__ import annotations

import json
import pytest

from app.agent.intent import explicit_customer_name, bind_skill_customer_name
from app.agent.graph import reason_and_select, execute_selected_tools, graph_input
from app.agent.evidence import trusted_identifiers
from evals.run_w13 import INPUT
from evals.w13_scoring import score_agent_case
from tests.test_nvidia_workflow_contract import ctx
from tests.test_w09_escalation_skill import (
    FakeMCP, SKILL_NAME, issue, CRITICAL_ID, CUSTOMER_ID,
)


@pytest.mark.parametrize("question,expected", [
    ("For Acme Retail, use the escalation Skill to assess customer risk.", "Acme Retail"),
    ("Regarding Meridian Logistics, please assess escalation risk.", "Meridian Logistics"),
    ("Assess escalation risk for Northstar Finance.", "Northstar Finance"),
    ("What is Acme Retail's escalation risk?", "Acme Retail"),
    ("In one sentence, define customer escalation in general.", None),
    ("For a customer, use the escalation Skill.", None),
])
def test_customer_name_only_from_explicit_user_request(question, expected):
    assert explicit_customer_name([{"role": "user", "content": question}]) == expected


def test_missing_skill_input_can_be_bound_from_user_without_fixture_mapping():
    q = [{"role":"user", "content":"For Meridian Logistics, use the escalation Skill."}]
    args, status = bind_skill_customer_name(SKILL_NAME, {}, q)
    assert args == {"customer_name": "Meridian Logistics"}
    assert status == "BOUND_FROM_EXPLICIT_CUSTOMER_NAME"
    # Never recover from an assistant/model claim made in an earlier turn.
    assert bind_skill_customer_name(SKILL_NAME, {}, [
        {"role":"user", "content":"What is the risk?"}])[0] == {}


def test_conflicting_model_customer_name_rejected_without_substitution():
    q = [{"role":"user", "content":"For Acme Retail, use the Skill."}]
    args, status = bind_skill_customer_name(
        SKILL_NAME, {"customer_name":"Northstar Finance"}, q)
    assert args["customer_name"] == "Northstar Finance"
    assert status == "CUSTOMER_NAME_MISMATCH_WITH_USER_REFERENCE"


def test_model_placeholder_dropped_only_when_explicit_name_is_available():
    q = [{"role":"user","content":"For Acme Retail, use the Skill."}]
    args, status = bind_skill_customer_name(
        SKILL_NAME, {"customer_id":"customer-001"}, q)
    assert args == {"customer_name":"Acme Retail"}
    assert status == "BOUND_FROM_EXPLICIT_CUSTOMER_NAME"


@pytest.mark.asyncio
async def test_ev04_model_selected_empty_arguments_executes_real_scoped_skill():
    question = ("For Acme Retail, use the customer_escalation_summary Skill to "
                "assess customer risk and recommend a next action, showing "
                "sources and missing information.")
    mcp = FakeMCP([issue()])
    state = graph_input(question)
    state["messages"].append({"role":"assistant", "tool_calls":[
        {"function":{"name":SKILL_NAME,"arguments":{}}}]})
    outcome = await execute_selected_tools(state, ctx("sales_user", mcp))
    assert [name for name, _ in mcp.calls] == [
        "find_customer", "list_open_issues", "get_issue_history"]
    assert mcp.calls[0][1] == {"customer_name":"Acme Retail"}
    assert [event["name"] for event in outcome["tool_events"]] == [
        "find_customer", "list_open_issues", "get_issue_history", SKILL_NAME]
    assert outcome["tool_events"][-1]["status"] == "ok"
    assert (outcome["tool_events"][-1]["argument_resolution"] ==
            "BOUND_FROM_EXPLICIT_CUSTOMER_NAME")
    assert "issues:"+CRITICAL_ID in outcome["evidence_refs"]

    # The evidence-only synthesis should not need another model inference.
    state["messages"] += outcome["messages"]
    state["model_turns"] = 1
    state["proposed_actions"] = outcome["proposed_actions"]
    finished = await reason_and_select(state, ctx("sales_user", mcp))
    assert finished["status"] == "complete"
    assert "Critical" in finished["answer"]
    assert "Missing information" in finished["answer"]
    case = next(c for c in json.loads(INPUT.read_text())["cases"]
                if c["id"] == "EV04-sales-escalation")
    scored = score_agent_case(case, {
        "status": finished["status"], "answer": finished["answer"],
        "tool_events": outcome["tool_events"], "evidence_refs": outcome["evidence_refs"],
        "proposed_actions": outcome["proposed_actions"],
        "grounded_identifiers": sorted(trusted_identifiers(state["messages"])),
    })
    assert scored["passed"], scored["checks"]


@pytest.mark.asyncio
async def test_ev04_denied_customer_lookup_never_leaks_other_customer_issues():
    mcp = FakeMCP([issue()], errors={"find_customer":"forbidden"})
    state = graph_input("For Restricted Company, use the escalation Skill.")
    state["messages"].append({"role":"assistant", "tool_calls":[
        {"function":{"name":SKILL_NAME,"arguments":{}}}]})
    outcome = await execute_selected_tools(state,ctx("sales_user",mcp))
    assert [name for name,_ in mcp.calls] == ["find_customer"]
    assert outcome["evidence_refs"] == []
    assert outcome["tool_events"][-1]["status"] == "unavailable"
    assert not outcome["proposed_actions"]


@pytest.mark.asyncio
async def test_name_mismatch_never_calls_authenticated_mcp():
    mcp = FakeMCP([issue()])
    state = graph_input("For Acme Retail, use the escalation Skill.")
    state["messages"].append({"role":"assistant", "tool_calls":[
        {"function":{"name":SKILL_NAME,
                     "arguments":{"customer_name":"Northstar Finance"}}}]})
    outcome = await execute_selected_tools(state,ctx("sales_user",mcp))
    assert not mcp.calls
    assert outcome["tool_events"][-1]["status"] == "validation_error"
    assert outcome["tool_events"][-1]["error_code"] == \
           "CUSTOMER_NAME_MISMATCH_WITH_USER_REFERENCE"
