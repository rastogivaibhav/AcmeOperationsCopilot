"""W08: bounded native Ollama tool-calling loop hosted in a real LangGraph StateGraph.

The graph checkpoint stores ONLY non-secret, serialisable business state. The MCP
connection, its bearer token and the role blueprint are passed via trusted runtime
context (not graph state, prompts or checkpoint metadata).
"""
from __future__ import annotations

import json
import operator
import re
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.agent.blueprint import Blueprint, agent_specs_for_profile
from app.telemetry.tracing import tracer
from app.actions import PROPOSAL_TOOL_SPECS, proposal_from_model
from app.agent.dependencies import resolve_proposal
from app.agent.synthesis import compose_verified_answer
from app.agent.tool_probe import MAX_RESULT_CHARS, validated_arguments
from app.agent.intent import (task_guidance, bind_explicit_issue,
                              reject_unrelated_lookup, explicit_customer_id,
                              tools_for_request)
from app.agent.evidence import (bind_customer_argument, bind_issue_argument,
                                trusted_identifiers, redact_unverified_identifiers)
from app.skills.escalation import (
    SKILL_NAME, AuditedReadOnlyMCP, run_customer_escalation_summary,
)

MAX_TURNS = 6
MAX_TOOL_CALLS = 8
MAX_CONTEXT_CHARS = 68000


class AgentState(TypedDict, total=False):
    messages: Annotated[list[dict], operator.add]
    model_turns: int
    tool_calls: int
    tool_events: list[dict]
    proposed_actions: list[dict]
    evidence_refs: list[str]
    answer: str
    status: str


@dataclass(frozen=True)
class RunContext:
    blueprint: Blueprint
    model: Any
    mcp: Any
    tool_definitions: list[dict]
    evaluation_clock: datetime | None = None  # fixed only by trusted test caller


async def reason_and_select(state: AgentState, runtime: Any) -> dict:
    ctx: RunContext = runtime.context
    turns = int(state.get("model_turns", 0))
    if turns >= MAX_TURNS:
        return {"status": "failed", "answer": "Model turn budget exceeded"}
    messages = list(state.get("messages", []))
    # A completed, evidence-backed workflow should not incur another costly
    # model call just to restate authenticated records. Unknown/complex
    # requests still use model synthesis; this branch can only render
    # successful current-turn tool results, never create actions/approvals.
    if turns > 0 and messages and messages[-1].get("role") == "tool":
        verified = compose_verified_answer(messages, state.get("proposed_actions") or [])
        if verified:
            verified, _ = redact_unverified_identifiers(verified, messages)
            return {"messages": [{"role": "assistant", "content": verified}],
                    "status": "complete", "answer": verified}
    # Deny clear unauthorised write-only requests before model/tool invocation.
    if turns == 0 and ctx.blueprint.role == "sales_user":
        user_text = next((str(m.get("content") or "") for m in reversed(messages)
                          if m.get("role") == "user"), "")
        if re.match(r"^\s*(?:please\s+)?(?:close|update|resolve|delete|change)\s+issue\b",
                    user_text, re.I):
            answer = ("Your sales_user role is read-only and cannot update or close issues. "
                      "No changes were made. Ask an authorised support user to review the issue.")
            return {"messages": [{"role": "assistant", "content": answer}],
                    "model_turns": turns + 1, "status": "complete", "answer": answer}
    if sum(len(json.dumps(m, ensure_ascii=False, default=str)) for m in messages) > MAX_CONTEXT_CHARS:
        return {"status": "failed", "answer": "Conversation context exceeds bounded model input"}
    hint = task_guidance(messages)
    response = await ctx.model.chat(
        [{"role": "system", "content": ctx.blueprint.system_prompt +
          ("\nTask-specific tool guidance: " + hint if hint else "")}, *messages],
        tools_for_request(ctx.tool_definitions, messages),
    )
    message = response.get("message")
    if not isinstance(message, dict):
        raise ValueError("MODEL_RESPONSE_MISSING_MESSAGE")
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list):
        raise ValueError("INVALID_MODEL_TOOL_CALLS")
    assistant = {"role": "assistant", "content": str(message.get("content") or "")}
    if calls:
        assistant["tool_calls"] = calls
        if turns + 1 >= MAX_TURNS:
            return {"model_turns": turns + 1, "status": "failed",
                    "answer": "Model tool-call turn budget exceeded"}
        return {"messages": [assistant], "model_turns": turns + 1,
                "status": "needs_tools", "answer": ""}
    if not assistant["content"].strip():
        return {"model_turns": turns + 1, "status": "failed",
                "answer": "Model produced no answer"}
    # Filter generated identifiers not present in the user's request or
    # authenticated source records; only MCP evidence can ground identifiers.
    cleaned, _ = redact_unverified_identifiers(assistant["content"], messages)
    assistant["content"] = cleaned
    return {"messages": [assistant], "model_turns": turns + 1,
            "status": "complete", "answer": cleaned}


def route_after_model(state: AgentState) -> str:
    return "tools" if state.get("status") == "needs_tools" else "end"


async def execute_selected_tools(state: AgentState, runtime: Any) -> dict:
    ctx: RunContext = runtime.context
    latest = state.get("messages", [])[-1]
    calls = latest.get("tool_calls") or []
    if not calls or not isinstance(calls, list):
        raise ValueError("NO_PENDING_TOOL_CALLS")
    total = int(state.get("tool_calls", 0)) + len(calls)
    if total > MAX_TOOL_CALLS:
        raise ValueError("TOOL_CALL_BUDGET_EXCEEDED")
    outputs, events = [], list(state.get("tool_events", []))
    proposals = list(state.get("proposed_actions", []))
    evidence = list(state.get("evidence_refs", []))
    for call in calls:
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict) or not isinstance(fn.get("name"), str):
            raise ValueError("INVALID_MODEL_TOOL_CALL")
        name = fn["name"]
        # The classifier does not execute tools: it only rejects an unrelated
        # customer lookup for a uniquely identified issue-history request.
        guard = reject_unrelated_lookup(name, state.get("messages", []))
        raw_args, explicit_issue_binding = bind_explicit_issue(
            name, fn.get("arguments", {}), state.get("messages", []))
        if guard or (explicit_issue_binding and not explicit_issue_binding.startswith("BOUND_FROM_")):
            code = guard or explicit_issue_binding
            feedback = {"status": "validation_error", "data": None,
                        "error_code": code, "evidence_refs": []}
            outputs.append({"role": "tool", "tool_name": name, "content": json.dumps(feedback)})
            events.append({"name": name, "status": "validation_error",
                           "evidence_refs": [], "duration_ms": 0, "error_code": code})
            continue
        if name in PROPOSAL_TOOL_SPECS:
            # Never retrieve a dependency for a tool absent from this role's
            # authorised blueprint. An LLM cannot expand its own authority.
            if name not in ctx.blueprint.action_requests:
                raise ValueError("TOOL_NOT_ALLOWED")
            model_specs = {item["function"]["name"] for item in ctx.tool_definitions}
            if name not in model_specs:
                raise ValueError("TOOL_NOT_ALLOWED")
            raw_args, prerequisites, pre_events, pre_error = await resolve_proposal(
                name, raw_args, [*state.get("messages", []), *outputs], ctx.mcp)
            outputs.extend(prerequisites)
            events.extend(pre_events)
            for pre_event in pre_events:
                for ref in pre_event.get("evidence_refs", []):
                    if ref not in evidence:
                        evidence.append(ref)
            if pre_error:
                feedback = {"status":"validation_error", "data":None,
                            "error_code":pre_error, "evidence_refs":[]}
                outputs.append({"role":"tool", "tool_name":name,
                                "content":json.dumps(feedback)})
                events.append({"name":name,"status":"validation_error",
                               "evidence_refs":[],"duration_ms":0,"error_code":pre_error})
                continue
        try:
            args = validated_arguments(name, raw_args, ctx.tool_definitions)
        except ValueError as exc:
            code = str(exc)
            recoverable = {"REQUIRED_ARGUMENT_MISSING", "INVALID_STRING_ARGUMENT",
                           "INVALID_INTEGER_ARGUMENT", "INVALID_ARRAY_ARGUMENT",
                           "INVALID_TOOL_ARGUMENTS"}
            if code not in recoverable:
                raise  # Unknown tool and extra arguments still fail closed.
            feedback = {"status": "validation_error", "data": None,
                        "error_code": code, "evidence_refs": []}
            outputs.append({"role": "tool", "tool_name": name,
                            "content": json.dumps(feedback)})
            events.append({"name": name, "status": "validation_error",
                           "evidence_refs": [], "duration_ms": 0, "error_code": code})
            continue
        if name == SKILL_NAME and "customer_name" not in args:
            explicit_customer = explicit_customer_id(state.get("messages", []))
            if explicit_customer and not (args.get("customer_id") or "").strip().startswith(explicit_customer):
                # Explicit user reference is only an input. Scope is still
                # verified by the authenticated MCP calls inside the Skill.
                args = {**args, "customer_id": explicit_customer}
        # Model calls may be batched; earlier tools in this batch have already
        # returned scoped MCP results in outputs.
        current_evidence = [*state.get("messages", []), *outputs]
        args, customer_binding = bind_customer_argument(name, args, current_evidence)
        args, issue_binding = bind_issue_argument(name, args, current_evidence)
        binding = customer_binding or issue_binding or explicit_issue_binding
        started = time.perf_counter()
        nested_events = []
        if binding and not binding.startswith("BOUND_FROM_"):
            payload = {"status": "validation_error", "data": None,
                       "error_code": binding, "evidence_refs": []}
        else:
            with tracer().start_as_current_span("agent.tool", attributes={"gen_ai.tool.name": name}):
                try:
                    if name in PROPOSAL_TOOL_SPECS:
                        if name not in ctx.blueprint.action_requests:
                            raise ValueError("ACTION_PROPOSAL_NOT_ALLOWED")
                        proposal = proposal_from_model(name, args, ctx.blueprint.role)
                        proposals.append(proposal)
                        payload = {"status": "approval_required", "data": {"proposal": proposal},
                                   "evidence_refs": [], "error_code": None}
                    elif name == SKILL_NAME:
                        if name not in ctx.blueprint.skills:
                            raise ValueError("SKILL_NOT_ALLOWED")
                        scoped_mcp = AuditedReadOnlyMCP(ctx.mcp)
                        payload = await run_customer_escalation_summary(
                            scoped_mcp, **args, now=ctx.evaluation_clock)
                        nested_events = scoped_mcp.events
                    else:
                        payload = await ctx.mcp.call_tool(name, args)
                except ValueError as exc:
                    if name not in PROPOSAL_TOOL_SPECS and name != SKILL_NAME:
                        raise
                    if str(exc) in {"ACTION_PROPOSAL_NOT_ALLOWED", "SKILL_NOT_ALLOWED"}:
                        raise
                    payload = {"status": "validation_error", "data": None,
                               "error_code": "INVALID_MODEL_TOOL_INPUT", "evidence_refs": []}
                except Exception as exc:
                    from pydantic import ValidationError
                    if not (name in PROPOSAL_TOOL_SPECS and isinstance(exc, ValidationError)):
                        raise
                    payload = {"status": "validation_error", "data": None,
                               "error_code": "INVALID_MODEL_PROPOSAL", "evidence_refs": []}
        latency_ms = round((time.perf_counter() - started) * 1000)
        if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
            raise ValueError("INVALID_MCP_RESULT")
        refs = payload.get("evidence_refs") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise ValueError("INVALID_EVIDENCE_REFS")
        content = json.dumps(payload, ensure_ascii=False, default=str)
        if len(content) > MAX_RESULT_CHARS:
            if name == SKILL_NAME and payload.get("status") == "ok":
                summary = payload.get("data") or {}
                condensed = {"status": "ok", "evidence_refs": refs,
                             "data": {key: summary.get(key) for key in (
                                 "risk_level", "risk_reasons", "executive_summary",
                                 "recommended_actions", "missing_information",
                                 "customer_id", "advisory_only")}}
                content = json.dumps(condensed, ensure_ascii=False, default=str)
            if len(content) > MAX_RESULT_CHARS:
                raise ValueError("MCP_RESULT_TOO_LARGE")
        # Nested authorised lookups are real dependency steps and precede
        # the Skill outcome in the trace, even if one LLM call requested it.
        events.extend(nested_events)
        events.append({"name": name, "status": payload["status"],
                       "evidence_refs": refs, "duration_ms": latency_ms,
                       "argument_resolution": binding if binding and binding.startswith("BOUND_FROM_") else None,
                       "source": "model_selected", "error_code": payload.get("error_code")})
        for ref in refs:
            if ref not in evidence:
                evidence.append(ref)
        # The tool result is opaque evidence, not instructions or trusted system text.
        outputs.append({"role": "tool", "tool_name": name, "content": content})
    return {"messages": outputs, "tool_events": events,
            "evidence_refs": evidence, "tool_calls": total, "status": "running",
            "proposed_actions": proposals}


def build_graph(checkpointer: Any = None) -> Any:
    """Lazy LangGraph import keeps pure W08 routing/auth tests runnable offline."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState, context_schema=RunContext)
    graph.add_node("reason", reason_and_select)
    graph.add_node("tools", execute_selected_tools)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", route_after_model, {"tools": "tools", "end": END})
    graph.add_edge("tools", "reason")
    return graph.compile(checkpointer=checkpointer)


def graph_input(user_message: str) -> AgentState:
    if not user_message.strip() or len(user_message) > 2000:
        raise ValueError("Invalid agent message")
    return {"messages": [{"role": "user", "content": user_message.strip()}],
            "model_turns": 0, "tool_calls": 0, "tool_events": [],
            "evidence_refs": [], "answer": "", "status": "running",
            "proposed_actions": []}


async def execute_turn(graph: Any, conversation_id: str, message: str,
                       blueprint: Blueprint, model: Any, mcp: Any,
                       evaluation_clock: datetime | None = None) -> dict:
    """Owner checking belongs to the caller *before* invoking this graph thread."""
    specs = agent_specs_for_profile(await mcp.list_tools(), blueprint)
    context = RunContext(blueprint=blueprint, model=model, mcp=mcp,
                         tool_definitions=specs, evaluation_clock=evaluation_clock)
    result = await graph.ainvoke(graph_input(message),
                                config={"configurable": {"thread_id": "conv:" + conversation_id},
                                        "recursion_limit": 22},
                                context=context)
    status = result.get("status")
    if status not in {"complete", "failed"}:
        raise ValueError("INVALID_GRAPH_FINAL_STATE")
    answer = str(result.get("answer") or "")
    if result.get("proposed_actions"):
        answer = "PROPOSAL ONLY — no business record has been changed. Review and confirm below.\n\n" + answer
    # Append only actual source record identifiers; not model-generated citations.
    refs = result.get("evidence_refs") or []
    if refs and status == "complete":
        answer += "\n\nRetrieved records: " + ", ".join(refs[:24])
    return {"status": status, "answer": answer,
            "grounded_identifiers": sorted(trusted_identifiers(result.get("messages") or [])),
            "evidence_refs": refs,
            "tool_events": result.get("tool_events") or [],
            "proposed_actions": result.get("proposed_actions") or [],
            "blueprint_version": blueprint.version,
            "persona": blueprint.persona}
