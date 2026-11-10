"""W10 focused offline tests. PostgreSQL/Keycloak/MCP live checks are separate."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import sys
import types
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from acme_shared.policies import Principal
from app.actions import ALLOWED_TRANSITIONS, WriteIntent, proposal_from_model
from app.agent.blueprint import agent_specs_for_profile, load_blueprint
from app.agent.graph import RunContext, execute_selected_tools, graph_input
from tests.test_w08_blueprints import TOOL_DEFINITIONS

ISSUE = "ab000000-0000-4000-8000-000000000002"
APPROVAL = uuid.UUID("ab000000-0000-4000-8000-000000000099")
OPERATION = uuid.UUID("ab000000-0000-4000-8000-000000000098")


def principal(role, sub="user-1"):
    return Principal(sub=sub, roles=frozenset({role}))


def issue_intent(**overrides):
    args = {"kind": "issue_update", "issue_id": ISSUE,
            "new_status": "investigating", "expected_version": 1,
            "note": "Customer confirmed issue is actively investigated"}
    args.update(overrides)
    return WriteIntent(**args)


def action_intent(**overrides):
    args = {"kind": "next_action", "issue_id": ISSUE,
            "description": "Confirm outstanding evidence with account owner"}
    args.update(overrides)
    return WriteIntent(**args)


@pytest.mark.parametrize("kind,role,allowed", [
    ("issue_update", "sales_user", False),
    ("issue_update", "support_user", True),
    ("issue_update", "admin", True),
    ("next_action", "sales_user", False),
    ("next_action", "support_user", False),
    ("next_action", "admin", True),
])
def test_write_intent_roles(kind, role, allowed):
    request = issue_intent() if kind == "issue_update" else action_intent()
    if allowed:
        request.require_role(principal(role))
    else:
        with pytest.raises(PermissionError, match="ROLE_DENIED"):
            request.require_role(principal(role))


@pytest.mark.parametrize("bad", [
    {"new_status": "nonsense"}, {"expected_version": 0},
    {"expected_version": None}, {"note": " "},
    {"description": "extra"}, {"operation_id": str(OPERATION)},
    {"issue_id": "not-uuid"},
])
def test_issue_write_validation_fails_closed(bad):
    with pytest.raises(ValidationError):
        issue_intent(**bad)


@pytest.mark.parametrize("bad", [
    {"description": "   "}, {"note": "unwanted"},
    {"new_status": "open"}, {"expected_version": 1},
    {"approval_id": str(APPROVAL)},
])
def test_next_action_validation_fails_closed(bad):
    with pytest.raises(ValidationError):
        action_intent(**bad)


def test_mcp_args_include_server_ids_only_after_confirmation():
    intent = issue_intent()
    assert "operation_id" not in intent.model_dump()
    tool, params = intent.args_for_mcp(str(APPROVAL), str(OPERATION))
    assert tool == "update_issue_status"
    assert params["approval_id"] == str(APPROVAL)
    assert params["expected_version"] == 1
    tool, params = action_intent().args_for_mcp(str(APPROVAL), str(OPERATION))
    assert tool == "create_next_action" and params["operation_id"] == str(OPERATION)


def test_agent_role_profiles_expose_only_proposals_not_mcp_writes():
    expected = {"sales_user": set(), "support_user": {"request_issue_update"},
                "admin": {"request_issue_update", "request_next_action"}}
    for role, action_names in expected.items():
        blueprint = load_blueprint(role)
        assert blueprint.action_requests == action_names
        actual = {x["function"]["name"] for x in
                  agent_specs_for_profile(TOOL_DEFINITIONS, blueprint)}
        assert action_names.issubset(actual)
        assert "create_next_action" not in actual and "update_issue_status" not in actual


def test_forged_sales_blueprint_cannot_add_write_proposal():
    sales = load_blueprint("sales_user")
    with pytest.raises(ValueError, match="BLUEPRINT_ACTION_ESCALATION"):
        agent_specs_for_profile(TOOL_DEFINITIONS,
                                replace(sales, action_requests=frozenset({"request_next_action"})))


def test_model_proposals_cannot_carry_operation_or_approval_ids():
    proposal = proposal_from_model("request_next_action",
                                   {"issue_id": ISSUE, "description": "Call owner"}, "admin")
    assert proposal["kind"] == "next_action"
    assert "operation_id" not in proposal and "approval_id" not in proposal
    with pytest.raises(PermissionError):
        proposal_from_model("request_next_action",
                            {"issue_id": ISSUE, "description": "Call owner"}, "support_user")


class FakeMCP:
    def __init__(self):
        self.calls = []
    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return {"status": "ok", "evidence_refs": []}


@pytest.mark.asyncio
async def test_graph_proposal_does_not_call_mcp_write():
    blueprint = load_blueprint("admin")
    mcp = FakeMCP()
    definitions = agent_specs_for_profile(TOOL_DEFINITIONS, blueprint)
    state = graph_input("Create a recommended next action")
    # The policy requires a verified history before drafting an action.
    state["messages"].append({"role":"tool","tool_name":"get_issue_history",
                              "content":json.dumps({"status":"ok",
                                  "data":{"issue":{"id": ISSUE, "status":"investigating",
                                                    "version":1},"updates":[]},
                                  "evidence_refs":["issues:"+ISSUE]})})
    state["messages"].append({"role": "assistant", "tool_calls": [{"function": {
        "name": "request_next_action",
        "arguments": {"issue_id": ISSUE, "description": "Ask owner for evidence"}}}]})
    runtime = SimpleNamespace(context=RunContext(blueprint, None, mcp, definitions))
    output = await execute_selected_tools(state, runtime)
    assert not mcp.calls
    assert output["tool_events"][0]["status"] == "approval_required"
    assert output["proposed_actions"][0]["kind"] == "next_action"
    assert "operation_id" not in output["proposed_actions"][0]


@pytest.mark.asyncio
async def test_sales_agent_refuses_forged_write_proposal_before_mcp_call():
    blueprint = load_blueprint("sales_user")
    mcp = FakeMCP()
    state = graph_input("Create an action")
    state["messages"].append({"role": "assistant", "tool_calls": [{"function": {
        "name": "request_next_action",
        "arguments": {"issue_id": ISSUE, "description": "Not authorised"}}}]})
    runtime = SimpleNamespace(context=RunContext(
        blueprint, None, mcp, agent_specs_for_profile(TOOL_DEFINITIONS, blueprint)))
    with pytest.raises(ValueError, match="TOOL_NOT_ALLOWED"):
        await execute_selected_tools(state, runtime)
    assert not mcp.calls


def test_transition_policy_cannot_close_closed_issue():
    assert ALLOWED_TRANSITIONS["closed"] == frozenset()
    assert "closed" not in ALLOWED_TRANSITIONS["open"]
    assert "investigating" in ALLOWED_TRANSITIONS["open"]


def test_w10_migration_and_api_have_explicit_boundaries():
    root = Path(__file__).resolve().parents[1]
    migration = (root / "database/migrations/versions/0003_controlled_writes.py").read_text()
    assert "issue_status_operations" in migration and "confirmed_at" in migration
    main = (root / "app/main.py").read_text()
    for endpoint in ('/api/actions/prepare', '/api/actions/{approval_id}/confirm'):
        assert endpoint in main
    assert "payload.confirmed is not True" in main
    assert "require_csrf(request, auth)" in main
    js = (root / "app/static/workspace.js").read_text()
    assert "innerHTML" not in js
    assert "action-confirm" in js
    mcp = (root / "mcp_server/server.py").read_text()
    assert 'def update_issue_status(' in mcp
    assert 'has_permission(actor, "update_issue_status")' in mcp


def import_repo(monkeypatch):
    """Allows repository unit tests even where psycopg wheels are unavailable."""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        stub = types.ModuleType("psycopg")
        rows = types.ModuleType("psycopg.rows")
        rows.dict_row = object()
        monkeypatch.setitem(sys.modules, "psycopg", stub)
        monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    return importlib.import_module("mcp_server.repository")


class FakeDB:
    def __init__(self, *, confirmed=True, current_version=1, current_status="open",
                 actor="user-1", new_status="investigating", note="Verified triage",
                 expired=False):
        self.queries = []
        self.last = None
        self.record = None
        self.confirmed = confirmed
        self.current_version = current_version
        self.current_status = current_status
        self.actor = actor
        self.new_status = new_status
        self.note = note
        self.expired = expired
        self.mutations = 0
        self.used = False
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def cursor(self): return self
    def execute(self, sql, params):
        self.queries.append((sql, params))
        if "FROM issue_status_operations WHERE operation_id" in sql:
            self.last = self.record
        elif "FROM approval_requests WHERE id" in sql:
            self.last = {"kind": "issue_update", "actor_sub": self.actor,
                         "issue_id": uuid.UUID(ISSUE), "new_status": self.new_status,
                         "expected_version": 1, "note": self.note,
                         "operation_id": OPERATION,
                         "expires_at": (datetime.now(timezone.utc)-timedelta(minutes=1)
                                        if self.expired else datetime.now(timezone.utc)+timedelta(minutes=3)),
                         "confirmed_at": datetime.now(timezone.utc) if self.confirmed else None,
                         "used_at": datetime.now(timezone.utc) if self.used else None}
        elif "FROM issues WHERE id" in sql:
            self.last = {"status": self.current_status, "version": self.current_version}
        elif "UPDATE issues SET status" in sql:
            self.mutations += 1
            self.current_status = self.new_status
            self.current_version += 1
            self.last = {"version": self.current_version}
        elif "INSERT INTO issue_status_operations" in sql:
            self.record = {"operation_id": OPERATION, "issue_id": uuid.UUID(ISSUE),
                           "actor_sub": self.actor, "previous_status": "open",
                           "new_status": self.new_status, "expected_version": 1,
                           "new_version": self.current_version, "note": self.note,
                           "update_id": uuid.uuid4(), "created_at": datetime.now(timezone.utc)}
            self.last = self.record
        else:
            self.last = None
        if "UPDATE approval_requests SET used_at" in sql:
            self.used = True
    def fetchone(self): return self.last


@pytest.mark.parametrize("kwargs,expected", [
    ({"confirmed": False}, "approval_required"),
    ({"expired": True}, "approval_required"),
    ({"current_version": 2}, "version_conflict"),
    ({"current_status": "closed"}, "invalid_transition"),
    ({"actor": "other-user"}, "approval_required"),
])
def test_repository_write_denies_bad_approval_or_stale_state(monkeypatch, kwargs, expected):
    repo = import_repo(monkeypatch)
    fake = FakeDB(**kwargs)
    monkeypatch.setattr(repo, "db_connection", lambda: fake)
    outcome, record = repo.update_issue_status(principal("support_user"),
        issue_id=uuid.UUID(ISSUE), new_status="investigating", expected_version=1,
        note="Verified triage", approval_id=APPROVAL, operation_id=OPERATION)
    assert outcome == expected and record is None
    assert fake.mutations == 0


def test_repository_atomic_update_and_replay_idempotency(monkeypatch):
    repo = import_repo(monkeypatch)
    fake = FakeDB()
    monkeypatch.setattr(repo, "db_connection", lambda: fake)
    args = dict(issue_id=uuid.UUID(ISSUE), new_status="investigating", expected_version=1,
                note="Verified triage", approval_id=APPROVAL, operation_id=OPERATION)
    first, receipt = repo.update_issue_status(principal("support_user"), **args)
    assert first == "ok" and receipt["new_version"] == 2
    assert fake.mutations == 1
    again, same_receipt = repo.update_issue_status(principal("support_user"), **args)
    assert again == "ok" and same_receipt == receipt and fake.mutations == 1
    other, nothing = repo.update_issue_status(principal("support_user", sub="other-user"), **args)
    assert other == "conflict" and nothing is None

class FakeApprovalDB:
    def __init__(self):
        self.row = None
        self.returned = None
        self.queries = []
        self.issue = {"status": "open", "version": 1}
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def cursor(self): return self
    def execute(self, sql, params):
        self.queries.append((sql, params))
        if "SELECT status,version FROM issues" in sql:
            self.returned = self.issue
        elif "INSERT INTO approval_requests" in sql:
            (aid, sub, issue_id, desc, op, expiry, kind, status, version, note) = params
            self.row = {"id": aid, "actor_sub": sub, "issue_id": issue_id,
                        "description": desc, "operation_id": op, "expires_at": expiry,
                        "kind": kind, "new_status": status, "expected_version": version,
                        "note": note, "confirmed_at": None, "used_at": None}
            self.returned = None
        elif "DELETE FROM approval_requests" in sql:
            self.returned = ({"id": self.row["id"]}
                             if self.row and self.row["id"] == params[0] and
                             self.row["actor_sub"] == params[1] and
                             self.row["confirmed_at"] is None else None)
            if self.returned:
                self.row = None
        elif "FROM approval_requests WHERE id" in sql:
            self.returned = (self.row if self.row and
                             self.row["id"] == params[0] and self.row["actor_sub"] == params[1]
                             else None)
        elif "UPDATE approval_requests SET confirmed_at" in sql:
            self.row["confirmed_at"] = datetime.now(timezone.utc)
            self.returned = None
        else:
            self.returned = None
    def fetchone(self): return self.returned


def get_action_service(monkeypatch, db):
    import_repo(monkeypatch)  # Ensures psycopg stub available without wheels.
    service = importlib.import_module("app.action_service")
    monkeypatch.setattr(service.psycopg, "connect", lambda *a, **kw: db, raising=False)
    monkeypatch.setenv("DATABASE_URL", "fake://test")
    return service


def test_prepare_then_confirm_is_two_separate_steps(monkeypatch):
    fake = FakeApprovalDB()
    service = get_action_service(monkeypatch, fake)
    actor = principal("support_user")
    prepared = service.prepare(actor, issue_intent(note="Verified triage"))
    assert prepared["status"] == "awaiting_confirmation"
    assert fake.row["confirmed_at"] is None
    assert fake.row["operation_id"] == uuid.UUID(prepared["operation_id"])
    intent, aid, oid = service.confirm(actor, uuid.UUID(prepared["approval_id"]))
    assert fake.row["confirmed_at"] is not None
    assert intent.kind == "issue_update" and intent.new_status == "investigating"
    assert aid == prepared["approval_id"] and oid == prepared["operation_id"]
    assert not any("UPDATE issues" in sql for sql, _ in fake.queries)


def test_prepare_denies_sales_before_database_touch(monkeypatch):
    fake = FakeApprovalDB()
    service = get_action_service(monkeypatch, fake)
    with pytest.raises(PermissionError):
        service.prepare(principal("sales_user"), issue_intent())
    assert not fake.queries


def test_confirmation_must_match_original_actor_and_current_role(monkeypatch):
    fake = FakeApprovalDB()
    service = get_action_service(monkeypatch, fake)
    prep = service.prepare(principal("admin"), action_intent())
    approval_id = uuid.UUID(prep["approval_id"])
    with pytest.raises(LookupError):
        service.confirm(principal("admin", sub="other-user"), approval_id)
    with pytest.raises(PermissionError):
        service.confirm(principal("support_user"), approval_id)
    assert fake.row["confirmed_at"] is None


def test_approval_can_be_cancelled_only_before_confirmation(monkeypatch):
    fake = FakeApprovalDB()
    service = get_action_service(monkeypatch, fake)
    prep = service.prepare(principal("admin"), action_intent())
    aid = uuid.UUID(prep["approval_id"])
    assert not service.cancel(principal("admin", sub="someone-else"), aid)
    assert service.cancel(principal("admin"), aid)
    assert fake.row is None
    second = service.prepare(principal("admin"), action_intent())
    aid2 = uuid.UUID(second["approval_id"])
    service.confirm(principal("admin"), aid2)
    assert not service.cancel(principal("admin"), aid2)


def test_stale_version_fails_at_prepare_not_only_commit(monkeypatch):
    fake = FakeApprovalDB()
    fake.issue["version"] = 2
    service = get_action_service(monkeypatch, fake)
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        service.prepare(principal("support_user"), issue_intent())
    assert fake.row is None

class FakeNextActionDB:
    def __init__(self, confirmed=True, actor="user-1"):
        self.confirmed = confirmed
        self.actor = actor
        self.created = None
        self.last = None
        self.writes = 0
        self.used = False
    def __enter__(self): return self
    def __exit__(self, *a): return None
    def cursor(self): return self
    def execute(self, sql, params):
        if "FROM next_actions WHERE operation_id" in sql:
            self.last = self.created
        elif "FROM approval_requests WHERE id" in sql:
            self.last = {"id": APPROVAL, "kind": "next_action",
                         "actor_sub": self.actor, "issue_id": uuid.UUID(ISSUE),
                         "description": "Confirm next steps", "operation_id": OPERATION,
                         "confirmed_at": datetime.now(timezone.utc) if self.confirmed else None,
                         "expires_at": datetime.now(timezone.utc)+timedelta(minutes=5),
                         "used_at": datetime.now(timezone.utc) if self.used else None}
        elif "INSERT INTO next_actions" in sql:
            self.writes += 1
            self.created = {"id": uuid.uuid4(), "issue_id": uuid.UUID(ISSUE),
                            "description": "Confirm next steps", "operation_id": OPERATION,
                            "created_by_sub": self.actor, "created_at": datetime.now(timezone.utc)}
            self.last = self.created
        elif "UPDATE approval_requests SET used_at" in sql:
            self.used = True
            self.last = None
        else:
            self.last = None
    def fetchone(self): return self.last


@pytest.mark.parametrize("confirmed, expected", [(False, "approval_required"), (True, "ok")])
def test_admin_mcp_next_action_honours_confirmation(monkeypatch, confirmed, expected):
    repo = import_repo(monkeypatch)
    fake = FakeNextActionDB(confirmed=confirmed)
    monkeypatch.setattr(repo, "db_connection", lambda: fake)
    status, row = repo.create_next_action(principal("admin"), issue_id=uuid.UUID(ISSUE),
        description="Confirm next steps", approval_id=APPROVAL, operation_id=OPERATION)
    assert status == expected
    assert (row is not None) == confirmed
    assert fake.writes == (1 if confirmed else 0)
    if confirmed:
        status2, replayed = repo.create_next_action(principal("admin"),
            issue_id=uuid.UUID(ISSUE), description="Confirm next steps",
            approval_id=APPROVAL, operation_id=OPERATION)
        assert status2 == "ok" and replayed == row and fake.writes == 1


def test_write_panel_visible_only_to_authorised_roles():
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    root = Path(__file__).resolve().parents[1]
    env = Environment(loader=FileSystemLoader(str(root / "app/templates")),
                      autoescape=select_autoescape(["html"]))
    template = env.get_template("workspace.html")
    for role in ("sales_user", "support_user", "admin"):
        html = template.render(role=role, username="Demo", agent_persona="Agent",
                               permissions=[], csrf_token="csrf")
        assert ('id="action-prepare-form"' in html) == (role != "sales_user")
        assert ('<option value="next_action">' in html) == (role == "admin")
