"""W08: bounded native Ollama tool-calling loop hosted in a real LangGraph StateGraph.

The graph checkpoint stores ONLY non-secret, serialisable business state. The MCP
connection, its bearer token and the role blueprint are passed via trusted runtime
context (not graph state, prompts or checkpoint metadata).
"""
from __future__ import annotations

import json
import operator
import time
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.agent.blueprint import Blueprint, agent_specs_for_profile
from app.telemetry.tracing import tracer
from app.actions import PROPOSAL_TOOL_SPECS, proposal_from_model
from app.agent.tool_probe import MAX_RESULT_CHARS, validated_arguments
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


async def reason_and_select(state: AgentState, runtime: Any) -> dict:
    ctx: RunContext = runtime.context
    turns = int(state.get("model_turns", 0))
    if turns >= MAX_TURNS:
        return {"status": "failed", "answer": "Model turn budget exceeded"}
    messages = list(state.get("messages", []))
    if sum(len(json.dumps(m, ensure_ascii=False, default=str)) for m in messages) > MAX_CONTEXT_CHARS:
        return {"status": "failed", "answer": "Conversation context exceeds bounded model input"}
    response = await ctx.model.chat(
        [{"role": "system", "content": ctx.blueprint.system_prompt}, *messages],
        ctx.tool_definitions,
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
    return {"messages": [assistant], "model_turns": turns + 1,
            "status": "complete", "answer": assistant["content"]}


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
        args = validated_arguments(name, fn.get("arguments", {}), ctx.tool_definitions)
        started = time.perf_counter()
        nested_events = []
        with tracer().start_as_current_span("agent.tool", attributes={"gen_ai.tool.name": name}):
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
                payload = await run_customer_escalation_summary(scoped_mcp, **args)
                nested_events = scoped_mcp.events
            else:
                payload = await ctx.mcp.call_tool(name, args)
        latency_ms = round((time.perf_counter() - started) * 1000)
        if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
            raise ValueError("INVALID_MCP_RESULT")
        refs = payload.get("evidence_refs") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise ValueError("INVALID_EVIDENCE_REFS")
        content = json.dumps(payload, ensure_ascii=False, default=str)
        if len(content) > MAX_RESULT_CHARS:
            raise ValueError("MCP_RESULT_TOO_LARGE")
        events.append({"name": name, "status": payload["status"],
                       "evidence_refs": refs, "duration_ms": latency_ms,
                       "error_code": payload.get("error_code")})
        events.extend(nested_events)
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
                       blueprint: Blueprint, model: Any, mcp: Any) -> dict:
    """Owner checking belongs to the caller *before* invoking this graph thread."""
    specs = agent_specs_for_profile(await mcp.list_tools(), blueprint)
    context = RunContext(blueprint=blueprint, model=model, mcp=mcp,
                         tool_definitions=specs)
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
    return {"status": status, "answer": answer,
            "evidence_refs": result.get("evidence_refs") or [],
            "tool_events": result.get("tool_events") or [],
            "proposed_actions": result.get("proposed_actions") or [],
            "blueprint_version": blueprint.version,
            "persona": blueprint.persona}
