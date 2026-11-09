"""Acme Operations Copilot W11/W12 — identity-aware, observable agent runtime."""
from __future__ import annotations

import os
import asyncio
import secrets
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

import httpx2
import psycopg
from anyio import to_thread
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from acme_shared.policies import effective_role, has_permission, ROLE_PERMISSIONS
from app.auth.oidc import AuthContext, authenticated, require_csrf, router as oidc_router
from app.conversations import NewConversation
from app.auth.oidc import redis_client
from app.agent.blueprint import load_blueprint
from app.agent.graph import build_graph, execute_turn
from app.agent.transports import AuthenticatedMCP, OllamaChat
from app import conversations as conversations_store
from app import action_service
from app.actions import WriteIntent
from app.telemetry import store as telemetry
from app.telemetry.tracing import configure_tracing, tracer

_logger = logging.getLogger("acme.requests")

@asynccontextmanager
async def lifespan(instance: FastAPI):
    configure_tracing()
    # Postgres checkpointer lives for the entire application lifespan; the MCP
    # access token is passed only as short-lived run context, never checkpointed.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    database_url = os.environ["DATABASE_URL"]
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    # On startup, identify runs whose process died before a terminal status.
    # The LangGraph checkpoint remains available for a later owner-authorised turn.
    await to_thread.run_sync(telemetry.mark_interrupted_runs)
    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()
        instance.state.agent_graph = build_graph(checkpointer)
        yield


app = FastAPI(title="Acme Operations Copilot", version="0.6.0", lifespan=lifespan)
app.include_router(oidc_router)
_BASE = Path(__file__).resolve().parent
_templates = Environment(loader=FileSystemLoader(str(_BASE / "templates")),
                         autoescape=select_autoescape(["html", "xml"]))
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")


class ApprovalRequest(BaseModel):
    issue_id: uuid.UUID
    description: str = Field(min_length=1, max_length=1000)
    confirmed: bool  # Explicit user action; never an LLM tool argument.


@app.middleware("http")
async def request_telemetry(request: Request, call_next):
    """Correlated request logs contain route/path only, never queries or credentials."""
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", None) or request.url.path
        _logger.info(json.dumps({
            "event": "http_request", "request_id": request_id,
            "method": request.method, "route": str(route)[:160], "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }))


@app.middleware("http")
async def browser_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith(("/api/", "/auth/", "/app", "/login")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def landing():
    return _templates.get_template("landing.html").render()


@app.get("/app", response_class=HTMLResponse)
async def workspace(request: Request):
    try:
        auth = await authenticated(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        raise
    role = effective_role(auth.principal)
    blueprint = load_blueprint(role)
    html = _templates.get_template("workspace.html").render(
        username=auth.principal.username, role=role, agent_persona=blueprint.persona,
        permissions=sorted(ROLE_PERMISSIONS[role]),
        csrf_token=auth.csrf_token or "", via_cookie=auth.via_cookie,
    )
    return HTMLResponse(html)


@app.get("/healthz")
async def health():
    return {"status": "ok", "agent_runtime": "langgraph"}


@app.get("/readyz")
async def ready():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM customers")
                count = cursor.fetchone()[0]
        return {"status": "ok", "seeded_customer_count": count,
                "note": "MCP, Keycloak and Ollama must be tested in live smoke"}
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc


@app.get("/api/me")
async def me(auth: Annotated[AuthContext, Depends(authenticated)]):
    role = effective_role(auth.principal)
    return {"sub": auth.principal.sub, "username": auth.principal.username,
            "role": role, "capabilities": sorted(ROLE_PERMISSIONS.get(role, [])),
            "verified": True, "csrf_token": auth.csrf_token if auth.via_cookie else None}


@app.get("/api/customers/find")
async def customer_lookup(name: str, auth: Annotated[AuthContext, Depends(authenticated)]):
    """Real MCP request; MCP server independently verifies token and resource scope."""
    if not has_permission(auth.principal, "find_customer"):
        raise HTTPException(403, "Role not permitted")
    if not name.strip() or len(name) > 160:
        raise HTTPException(422, "Invalid customer name")
    url = os.getenv("MCP_URL", "http://mcp:8001/mcp")
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {auth.access_token}"},
                                  timeout=httpx2.Timeout(30.0, read=300.0)) as client:
        async with Client(streamable_http_client(url, http_client=client)) as session:
            call = await session.call_tool("find_customer", {"customer_name": name.strip()})
    if call.is_error:
        raise HTTPException(502, "MCP tool error")
    return {"mcp_result": call.model_dump(mode="json")}


@app.post("/api/approvals")
async def approve_next_action(request: Request, payload: ApprovalRequest,
                              auth: Annotated[AuthContext, Depends(authenticated)]):
    """Only a human-facing endpoint may issue approval receipts. No LLM tool here."""
    require_csrf(request, auth)
    actor = auth.principal
    if not has_permission(actor, "create_next_action"):
        raise HTTPException(403, "Admin role required")
    if not payload.description.strip():
        raise HTTPException(422, "Description is empty")
    if not payload.confirmed:
        raise HTTPException(422, "Explicit human confirmation required")
    approval_id, operation_id = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(os.environ["DATABASE_URL"]) as db, db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM issues WHERE id=%s", (payload.issue_id,))
        if not cursor.fetchone():
            raise HTTPException(404, "Issue not found")
        cursor.execute(
            "INSERT INTO approval_requests(id, actor_sub, issue_id, description, operation_id, expires_at, confirmed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,now())",
            (approval_id, actor.sub, payload.issue_id, payload.description.strip(), operation_id,
             datetime.now(timezone.utc) + timedelta(minutes=10)),
        )
    return {"approval_id": str(approval_id), "operation_id": str(operation_id),
            "issue_id": str(payload.issue_id), "expires_in_seconds": 600}


class PrepareActionRequest(BaseModel):
    intent: WriteIntent
    conversation_id: uuid.UUID | None = None


class ConfirmActionRequest(BaseModel):
    confirmed: bool  # Explicit human action, never set by an LLM or hidden JS callback.


@app.post("/api/actions/prepare", status_code=201)
async def prepare_action(request: Request, payload: PrepareActionRequest,
                         auth: Annotated[AuthContext, Depends(authenticated)]):
    """Creates an expiring, *unconfirmed* proposal; no business data is changed."""
    require_csrf(request, auth)
    try:
        payload.intent.require_role(auth.principal)
    except PermissionError as exc:
        await to_thread.run_sync(lambda: telemetry.log_policy_denial(
            actor_sub=auth.principal.sub, operation="prepare_" + payload.intent.kind))
        raise HTTPException(403, "Role not permitted") from exc
    if payload.conversation_id is not None:
        owned = await to_thread.run_sync(conversations_store.get_owned,
                                         auth.principal.sub, payload.conversation_id)
        if owned is None:
            raise HTTPException(404, "Conversation not found")
    try:
        return await to_thread.run_sync(action_service.prepare, auth.principal, payload.intent)
    except LookupError as exc:
        raise HTTPException(404, "Issue not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/actions/{approval_id}/confirm")
async def confirm_action(request: Request, approval_id: uuid.UUID, payload: ConfirmActionRequest,
                         auth: Annotated[AuthContext, Depends(authenticated)]):
    """Rechecks current role, confirms stored payload, then performs authenticated MCP commit."""
    require_csrf(request, auth)
    if payload.confirmed is not True:
        raise HTTPException(422, "Explicit user confirmation required")
    try:
        intent, approved_id, operation_id = await to_thread.run_sync(
            action_service.confirm, auth.principal, approval_id)
    except PermissionError as exc:
        raise HTTPException(403, "Role not permitted") from exc
    except LookupError as exc:
        raise HTTPException(404, "Approval not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    tool, args = intent.args_for_mcp(approved_id, operation_id)
    try:
        async with AuthenticatedMCP(auth.access_token) as mcp:
            result = await mcp.call_tool(tool, args)
    except Exception as exc:
        # The write may have committed before transport failure. Repeating confirmation
        # uses the SAME operation_id and is idempotent at the MCP/database boundary.
        raise HTTPException(503, "Write result uncertain; retry confirmation to reconcile") from exc
    if result.get("status") == "ok" and result.get("data"):
        return {"status": "committed", "operation_id": operation_id,
                "receipt": result["data"], "evidence_refs": result.get("evidence_refs", [])}
    error_status = result.get("status")
    if error_status in {"version_conflict", "conflict", "invalid_transition"}:
        raise HTTPException(409, {"status": error_status, "operation_id": operation_id})
    if error_status in {"forbidden", "approval_required"}:
        raise HTTPException(403, {"status": error_status})
    if error_status == "not_found":
        raise HTTPException(404, {"status": error_status})
    raise HTTPException(502, "MCP write could not be verified")


@app.delete("/api/actions/{approval_id}")
async def cancel_action(request: Request, approval_id: uuid.UUID,
                        auth: Annotated[AuthContext, Depends(authenticated)]):
    require_csrf(request, auth)
    cancelled = await to_thread.run_sync(action_service.cancel, auth.principal, approval_id)
    if not cancelled:
        raise HTTPException(409, "Approval cannot be cancelled or does not exist")
    return {"status": "cancelled"}


@app.get("/api/conversations")
def list_conversations(auth: Annotated[AuthContext, Depends(authenticated)]):
    return {"items": conversations_store.list_owned(auth.principal.sub)}


@app.post("/api/conversations", status_code=201)
def create_conversation(request: Request, payload: NewConversation,
                        auth: Annotated[AuthContext, Depends(authenticated)]):
    require_csrf(request, auth)
    if not payload.title.strip():
        raise HTTPException(422, "Conversation title required")
    role = effective_role(auth.principal)
    if role is None:
        raise HTTPException(403, "Role unavailable")
    return conversations_store.create_owned(
        auth.principal.sub, payload.title, load_blueprint(role).version)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID,
                     auth: Annotated[AuthContext, Depends(authenticated)]):
    item = conversations_store.get_owned(auth.principal.sub, conversation_id)
    if item is None:
        raise HTTPException(404, "Conversation not found")
    return item


@app.get("/api/activity/summary")
async def activity_summary(auth: Annotated[AuthContext, Depends(authenticated)]):
    return await to_thread.run_sync(lambda: telemetry.summary(owner_sub=auth.principal.sub))


@app.get("/api/activity/audit")
async def activity_audit(auth: Annotated[AuthContext, Depends(authenticated)], limit: int = 20):
    if not 1 <= limit <= 50:
        raise HTTPException(422, "Limit must be between 1 and 50")
    return {"items": await to_thread.run_sync(lambda: telemetry.list_business_audit(
        owner_sub=auth.principal.sub, limit=limit))}


@app.get("/api/activity/runs")
async def activity_runs(auth: Annotated[AuthContext, Depends(authenticated)],
                        limit: int = 20, conversation_id: uuid.UUID | None = None):
    if not 1 <= limit <= 50:
        raise HTTPException(422, "Limit must be between 1 and 50")
    if conversation_id is not None:
        owned = await to_thread.run_sync(
            conversations_store.get_owned, auth.principal.sub, conversation_id)
        if owned is None:
            raise HTTPException(404, "Conversation not found")
    items = await to_thread.run_sync(lambda: telemetry.list_runs(
        owner_sub=auth.principal.sub, limit=limit, conversation_id=conversation_id))
    return {"items": items}


@app.get("/api/activity/runs/{run_id}")
async def activity_run(run_id: uuid.UUID,
                       auth: Annotated[AuthContext, Depends(authenticated)]):
    result = await to_thread.run_sync(lambda: telemetry.get_run(
        owner_sub=auth.principal.sub, run_id=run_id))
    if result is None:
        raise HTTPException(404, "Execution not found")
    return result


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.post("/api/conversations/{conversation_id}/messages")
async def send_agent_message(request: Request, conversation_id: uuid.UUID,
                             payload: AgentMessageRequest,
                             auth: Annotated[AuthContext, Depends(authenticated)]):
    """Real LangGraph invocation, not a scripted answer or a direct MCP lookup."""
    require_csrf(request, auth)
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, "Message required")
    # Owner check BEFORE any LangGraph checkpoint or MCP tool access.
    owned = await to_thread.run_sync(
        conversations_store.get_owned, auth.principal.sub, conversation_id)
    if owned is None:
        raise HTTPException(404, "Conversation not found")
    role = effective_role(auth.principal)
    if role is None:
        raise HTTPException(403, "Role unavailable")
    blueprint = load_blueprint(role)
    # Never reuse a checkpoint under a different role or blueprint version.
    # The customer-scope revocation gate is deliberately deferred to W10/W16.
    if owned["blueprint_version"] != blueprint.version:
        raise HTTPException(409, "Agent profile changed; start a new investigation")
    # SET NX is a per-conversation concurrency gate; compare-delete prevents a
    # stale worker deleting another worker's lock. No unauthenticated lock keys.
    lock_id = secrets.token_urlsafe(24)
    lock_key = f"acme:agent:lock:{conversation_id}"
    store = redis_client()
    try:
        acquired = await store.set(lock_key, lock_id, nx=True, ex=900)
        if not acquired:
            raise HTTPException(409, "Conversation is processing another request")
        run_id = uuid.uuid4()
        run_started = time.perf_counter()
        run_created = False
        terminal_recorded = False
        try:
            receipt = await to_thread.run_sync(lambda: telemetry.create_run(
                conversation_id=conversation_id, owner_sub=auth.principal.sub,
                role=role, blueprint_version=blueprint.version,
                model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"), run_id=run_id))
            run_created = True
            # Bound the entire run before the 15-minute Redis lock lease expires.
            with tracer().start_as_current_span("agent.run", attributes={
                "acme.run.id": str(run_id), "acme.agent.role": role,
                "acme.agent.blueprint_version": blueprint.version,
            }):
                async with asyncio.timeout(840):
                    async with AuthenticatedMCP(auth.access_token) as mcp:
                        result = await execute_turn(request.app.state.agent_graph,
                                                    str(conversation_id), message,
                                                    blueprint, OllamaChat(), mcp)
            await to_thread.run_sync(lambda: conversations_store.store_turn(
                auth.principal.sub, conversation_id, message, result["answer"],
                successful=result["status"] == "complete",
                blueprint_version=result["blueprint_version"]))
            await to_thread.run_sync(lambda: telemetry.finish_run(
                run_id=run_id, owner_sub=auth.principal.sub,
                status="complete" if result["status"] == "complete" else "failed",
                duration_ms=round((time.perf_counter() - run_started) * 1000),
                tool_events=result.get("tool_events"),
                evidence_refs=result.get("evidence_refs"),
                error_code="AGENT_INCOMPLETE" if result["status"] != "complete" else None))
            terminal_recorded = True
            result["run_id"] = str(run_id)
            result["trace_id"] = receipt["trace_id"]
            return result
        except asyncio.CancelledError:
            if run_created and not terminal_recorded:
                try:
                    await to_thread.run_sync(lambda: telemetry.finish_run(
                        run_id=run_id, owner_sub=auth.principal.sub,
                        status="interrupted", duration_ms=round(
                            (time.perf_counter() - run_started) * 1000),
                        error_code="REQUEST_INTERRUPTED"))
                except Exception:
                    _logger.exception("Failed to persist cancelled run status")
            raise
        except HTTPException:
            raise
        except Exception as exc:
            if run_created and not terminal_recorded:
                try:
                    await to_thread.run_sync(lambda: telemetry.finish_run(
                        run_id=run_id, owner_sub=auth.principal.sub,
                        status="failed", duration_ms=round(
                            (time.perf_counter() - run_started) * 1000),
                        error_code="AGENT_EXECUTION_ERROR"))
                except Exception:
                    _logger.exception("Failed to persist failed run status")
            # Do not disclose tokens or raw tool payloads in an error response.
            raise HTTPException(502, "Agent execution failed; retry after checking runtime") from exc
        finally:
            try:
                await store.eval(
                    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                    "return redis.call('DEL', KEYS[1]) else return 0 end",
                    1, lock_key, lock_id,
                )
            except Exception:
                # Do not turn a successfully persisted business response into 500.
                # TTL still bounds the stale concurrency lock.
                import logging
                logging.getLogger(__name__).warning("Conversation lock release failed")
    finally:
        await store.aclose()
