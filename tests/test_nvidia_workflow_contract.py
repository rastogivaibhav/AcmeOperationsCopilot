"""NVIDIA-inspired typed request and governed workflow regression tests.

No model responses or live MCP outcomes are claimed by these unit tests.
"""
from types import SimpleNamespace
import pytest

from app.agent.intent import (analyse_request, task_guidance, bind_explicit_issue,
                              reject_unrelated_lookup)
from app.agent.graph import (RunContext, execute_selected_tools, graph_input)
from app.agent.blueprint import load_blueprint, agent_specs_for_profile
from app.skills.escalation import run_customer_escalation_summary, SKILL_NAME
from tests.test_w08_blueprints import TOOL_DEFINITIONS
from tests.test_w09_escalation_skill import FakeMCP as SkillMCP, issue, NOW, CUSTOMER_ID

ISSUE = "ab000000-0000-4000-8000-000000000001"


def call(name, **args):
    return {"function": {"name": name, "arguments": args}}


def ctx(role, mcp):
    bp = load_blueprint(role)
    return SimpleNamespace(context=RunContext(bp, None, mcp,
        agent_specs_for_profile(TOOL_DEFINITIONS, bp)))


class HistoryMCP:
    def __init__(self, status="ok", version=3):
        self.status, self.version = status, version
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        assert name == "get_issue_history"  # Proposal preconditions are read-only.
        if self.status != "ok":
            return {"status": self.status, "data": None, "evidence_refs": []}
        return {"status": "ok", "data": {
            "issue": {"id": ISSUE, "status": "investigating", "version": self.version},
            "updates": []}, "evidence_refs": ["issues:" + ISSUE]}


def test_typed_issue_signals_are_not_fixture_specific():
    custom = "123e4567-e89b-42d3-a456-426614174000"
    msgs = [{"role": "user", "content": f"Summarize history for issue {custom}."}]
    assert analyse_request(msgs).issue_id == custom
    assert analyse_request(msgs).purpose == "history"
    assert custom in task_guidance(msgs)
    assert reject_unrelated_lookup("find_customer", msgs) is not None
    args, tag = bind_explicit_issue("get_issue_history", {"issue_id": "placeholder"}, msgs)
    assert args["issue_id"] == custom and tag == "BOUND_FROM_EXPLICIT_USER_ISSUE"


def test_never_bind_multiple_or_mismatched_issue_identifiers():
    first, other = ISSUE, "ab000000-0000-4000-8000-000000000099"
    msgs = [{"role": "user", "content": f"Compare issues {first} and {other}"}]
    assert analyse_request(msgs).issue_id is None
    assert bind_explicit_issue("get_issue_history", {"issue_id": "bad"}, msgs)[1] is None
    one = [{"role": "user", "content": f"Inspect issue {first}"}]
    assert bind_explicit_issue("get_issue_history", {"issue_id": other}, one)[1] == \
        "ISSUE_ID_MISMATCH_WITH_USER_REFERENCE"


@pytest.mark.asyncio
async def test_skill_resolves_name_through_authenticated_mcp_without_bypassing_scope():
    mcp = SkillMCP([issue()])
    result = await run_customer_escalation_summary(mcp, customer_name="Acme Retail", now=NOW)
    assert result["status"] == "ok"
    assert result["data"]["risk_level"] == "Critical"
    assert [name for name, _ in mcp.calls] == [
        "find_customer", "list_open_issues", "get_issue_history"]
    assert result["data"]["advisory_only"] is True


@pytest.mark.asyncio
async def test_name_resolution_denial_does_not_disclose_issue_data():
    mcp = SkillMCP([issue()], errors={"find_customer": "forbidden"})
    result = await run_customer_escalation_summary(mcp, customer_name="Restricted", now=NOW)
    assert result["status"] == "unavailable"
    assert result["evidence_refs"] == []
    assert [name for name, _ in mcp.calls] == ["find_customer"]


@pytest.mark.asyncio
async def test_model_selected_named_skill_records_dependency_trajectory():
    mcp = SkillMCP([issue()])
    state = graph_input("Assess the escalation risk for Acme Retail")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call(SKILL_NAME, customer_name="Acme Retail")]})
    response = await execute_selected_tools(state, ctx("sales_user", mcp))
    assert [e["name"] for e in response["tool_events"]] == [
        "find_customer", "list_open_issues", "get_issue_history", SKILL_NAME]
    assert response["tool_events"][-1]["status"] == "ok"
    assert "issues:" + ISSUE in response["evidence_refs"]


@pytest.mark.asyncio
async def test_proposal_auto_fetches_authorised_history_and_binds_current_version():
    mcp = HistoryMCP()
    state = graph_input(f"Inspect issue {ISSUE} and propose changing status to open.")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("request_issue_update", issue_id=ISSUE, new_status="open",
             note="Confirm reconciliation") ]})
    result = await execute_selected_tools(state, ctx("support_user", mcp))
    assert mcp.calls == [("get_issue_history", {"issue_id": ISSUE})]
    assert [e["name"] for e in result["tool_events"]] == [
        "get_issue_history", "request_issue_update"]
    assert result["tool_events"][0]["source"] == "policy_precondition"
    assert result["tool_events"][1]["status"] == "approval_required"
    assert result["proposed_actions"][0]["expected_version"] == 3
    assert "issues:" + ISSUE in result["evidence_refs"]


@pytest.mark.asyncio
async def test_reject_stale_version_before_creating_model_proposal():
    mcp = HistoryMCP(version=4)
    state = graph_input(f"For issue {ISSUE} propose a status change.")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("request_issue_update", issue_id=ISSUE, new_status="open",
             expected_version=2, note="Check source")]})
    result = await execute_selected_tools(state, ctx("support_user", mcp))
    assert result["proposed_actions"] == []
    assert result["tool_events"][-1]["error_code"] == "STALE_PROPOSAL_ISSUE_VERSION"


@pytest.mark.asyncio
async def test_denied_history_never_generates_proposal():
    mcp = HistoryMCP(status="forbidden")
    state = graph_input(f"Create an action for issue {ISSUE}")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("request_next_action", issue_id=ISSUE, description="Contact owner")]})
    result = await execute_selected_tools(state, ctx("admin", mcp))
    assert result["proposed_actions"] == []
    assert result["tool_events"][-1]["error_code"] == "VERIFIED_ISSUE_HISTORY_REQUIRED"


@pytest.mark.asyncio
async def test_forged_approval_argument_does_not_trigger_lookup_or_proposal():
    mcp = HistoryMCP()
    state = graph_input(f"Create an action for issue {ISSUE}")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("request_next_action", issue_id=ISSUE, description="Call owner",
             approval_id="attacker-controlled")]})
    result = await execute_selected_tools(state, ctx("admin", mcp))
    assert result["tool_events"][-1]["error_code"] == "UNEXPECTED_ARGUMENT"
    assert result["proposed_actions"] == [] and not mcp.calls


@pytest.mark.asyncio
async def test_explicit_issue_history_binding_uses_user_uuid_not_guessed_id():
    mcp = HistoryMCP()
    state = graph_input(f"Read the history for issue {ISSUE}")
    state["messages"].append({"role": "assistant", "tool_calls": [
        call("get_issue_history", issue_id="invented")]})
    result = await execute_selected_tools(state, ctx("support_user", mcp))
    assert mcp.calls == [("get_issue_history", {"issue_id": ISSUE})]
    assert result["tool_events"][-1]["argument_resolution"] == "BOUND_FROM_EXPLICIT_USER_ISSUE"


def test_general_definition_does_not_become_escalation_tool_request():
    messages = [{"role": "user", "content":
                 "In one sentence, define customer escalation in general. Do not access customer records."}]
    assert analyse_request(messages).purpose == "general"
    assert "no customer tools" in task_guidance(messages)


def test_tool_trajectory_distinguishes_model_choice_from_dependencies():
    from evals.trajectory import inspect_trajectory
    events = [
        {"name": "get_issue_history", "status": "ok",
         "source": "policy_precondition"},
        {"name": "request_next_action", "status": "approval_required",
         "source": "model_selected"},
    ]
    result = inspect_trajectory(events)
    assert result["model_selected_tools"] == ["request_next_action"]
    assert result["policy_preconditions"] == ["get_issue_history"]
    assert result["argument_integrity_passed"]
    assert result["prerequisites_passed"]
    assert not inspect_trajectory(events[1:])["prerequisites_passed"]
    assert not inspect_trajectory([{"name": "list_open_issues",
                                   "status": "validation_error"}])["argument_integrity_passed"]


def test_business_fixture_guard_refuses_drift_without_looking_at_secret_rows(monkeypatch, tmp_path):
    from evals import fixture_guard
    baseline = tmp_path / "fixture-baseline.json"
    clean = {"sha256": "1234", "counts": dict(fixture_guard.EXPECTED_COUNTS),
             "mode": "read_only_business_fixture"}
    monkeypatch.setattr(fixture_guard, "fingerprint", lambda: clean)
    assert fixture_guard.check("capture", baseline)
    assert fixture_guard.check("verify", baseline)
    monkeypatch.setattr(fixture_guard, "fingerprint",
                        lambda: {**clean, "sha256": "different"})
    assert not fixture_guard.check("verify", baseline)


def test_intent_visibility_is_always_a_subset_of_existing_role_tools():
    from app.agent.intent import tools_for_request
    sales = load_blueprint("sales_user")
    specs = agent_specs_for_profile(TOOL_DEFINITIONS, sales)
    listed = lambda question: {item["function"]["name"] for item in tools_for_request(
        specs, [{"role": "user", "content": question}])}
    assert listed("Who owns the Acme Retail customer profile?") == {"find_customer"}
    assert listed("Which issues are currently open for Acme Retail?") == {
        "find_customer", "list_open_issues"}
    assert listed(f"Show the issue history for issue {ISSUE}") == {"get_issue_history"}
    assert listed("Define customer escalation in general.") == set()
    assert listed("Assess escalation for Acme Retail") == {
        "customer_escalation_summary"}
    assert "request_next_action" not in listed(f"Propose an action for issue {ISSUE}")



def test_explicit_customer_locator_can_reach_authenticated_skill_only():
    from app.agent.evidence import bind_customer_argument
    name = "customer_escalation_summary"
    arguments = {"customer_id": CUSTOMER_ID}
    args, error = bind_customer_argument(name, arguments, [
        {"role":"user","content":"Assess risk for customer ID "+CUSTOMER_ID}])
    assert args == arguments and error is None
    # Direct issue-list reads still require an authorised customer lookup.
    assert bind_customer_argument("list_open_issues",arguments,[])[1] == \
        "VERIFIED_CUSTOMER_ID_REQUIRED"


def test_proposal_visibility_uses_verified_policy_precondition():
    from app.agent.intent import tools_for_request
    bp = load_blueprint("admin")
    specs = agent_specs_for_profile(TOOL_DEFINITIONS,bp)
    visible = lambda question: {x["function"]["name"] for x in tools_for_request(
        specs, [{"role":"user","content":question}])}
    assert visible(f"Inspect issue {ISSUE} and propose changing its status to open") == {
        "request_issue_update"}
    assert visible(f"Inspect issue {ISSUE} and propose a next-action record") == {
        "request_next_action"}



def test_verified_synthesis_histories_include_source_updates_not_fake_resolution():
    from app.agent.synthesis import compose_verified_answer
    from tests.test_agent_grounding_recovery import tool_message
    msgs = [{"role":"user","content":"Show the conflicting issue history for issue "+ISSUE},
            tool_message("get_issue_history", {"issue":{
                "id": ISSUE, "status":"investigating", "priority":"critical"},
                "updates":[{"id":"ad000000-0000-4000-8000-000000000002",
                             "content":"Provisional fix sent"},
                            {"id":"ad000000-0000-4000-8000-000000000003",
                             "content":"Customer reports error still present"}]})]
    answer = compose_verified_answer(msgs, [])
    assert "still present" in answer and "not confirmed" in answer
    assert "ad000000-0000-4000-8000-000000000003" in answer
    assert compose_verified_answer(msgs[:1], []) is None


def test_verified_synthesis_skill_risk_and_missing_information_are_source_only():
    from app.agent.synthesis import compose_verified_answer
    from tests.test_agent_grounding_recovery import tool_message
    msgs = [{"role":"user","content":"Assess Acme Retail escalation risk"},
            tool_message(SKILL_NAME, {"advisory_only":True,
                "risk_level":"Critical", "executive_summary":"Two overdue issues",
                "risk_reasons":["SLA breached"],
                "recommended_actions":[{"action":"Contact support owner",
                                         "issue_id":ISSUE, "persisted":False}],
                "missing_information":["Confirmed remediation ETA absent"]})]
    answer = compose_verified_answer(msgs, [])
    assert "Critical" in answer and "SLA breached" in answer
    assert "remediation ETA" in answer
    assert "not saved" in answer
    denied = [msgs[0],tool_message(SKILL_NAME, None,status="forbidden")]
    assert compose_verified_answer(denied, []) is None


def test_verified_synthesis_proposals_require_source_issue_history():
    from app.agent.synthesis import compose_verified_answer
    from tests.test_agent_grounding_recovery import tool_message
    question = {"role":"user","content":"For issue "+ISSUE+" propose a next action"}
    proposal = {"kind":"next_action","issue_id":ISSUE,"description":"Confirm ETA"}
    assert compose_verified_answer([question], [proposal]) is None
    messages = [question,tool_message("get_issue_history", {
        "issue":{"id":ISSUE,"status":"investigating","version":1},
        "updates":[]})]
    answer = compose_verified_answer(messages,[proposal])
    assert "PROPOSAL ONLY" in answer and "Confirm ETA" in answer
    assert "not saved" in answer
    assert compose_verified_answer(messages,[{**proposal,"issue_id":
        "ab000000-0000-4000-8000-000000000099"}]) is None


@pytest.mark.asyncio
async def test_model_turn_finishes_from_verified_history_without_second_inference():
    from app.agent.graph import reason_and_select
    from tests.test_agent_grounding_recovery import tool_message
    class NeverCall:
        async def chat(self, messages, tools):
            raise AssertionError("A second model call was not needed")
    mcp=HistoryMCP()
    bp=load_blueprint("support_user")
    run=SimpleNamespace(context=RunContext(
        bp,NeverCall(),mcp,agent_specs_for_profile(TOOL_DEFINITIONS,bp)))
    state=graph_input("Retrieve history and conflicting updates for issue "+ISSUE)
    state["model_turns"]=1
    state["messages"] += [tool_message("get_issue_history",{
        "issue":{"id":ISSUE,"status":"investigating","priority":"critical"},
        "updates":[{"id":"ad000000-0000-4000-8000-000000000002",
                    "content":"Customer says issue still present"}]})]
    result=await reason_and_select(state,run)
    assert result["status"]=="complete" and "not confirmed" in result["answer"]


def test_never_synthesise_tool_data_from_other_conversation_turn():
    from app.agent.synthesis import compose_verified_answer
    from tests.test_agent_grounding_recovery import tool_message
    previous=tool_message("get_issue_history",{
        "issue":{"id":ISSUE,"status":"investigating"},
        "updates":[]})
    messages=[{"role":"user","content":"Issue "+ISSUE+" history"},previous,
              {"role":"user","content":"Issue "+ISSUE+" history now"}]
    assert compose_verified_answer(messages,[]) is None
