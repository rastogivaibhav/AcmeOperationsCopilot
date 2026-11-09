"""Offline tests: telemetry redaction, identity isolation and transport contracts."""
import uuid
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from app.telemetry.store import safe_label, safe_evidence_refs, sanitize_tool_events

ROOT = Path(__file__).resolve().parents[1]


def test_untrusted_messages_not_kept_in_event_telemetry():
    raw = [{"name": "find_customer", "status": "ok", "duration_ms": 7,
            "evidence_refs": ["issue:123", "secret token from user"],
            "arguments": {"password": "do-not-store"},
            "response": "Confidential customer details"}]
    events = sanitize_tool_events(raw)
    assert events == [{"tool_name": "find_customer", "status": "ok", "duration_ms": 7,
                       "error_code": None, "evidence_refs": ["issue:123"]}]
    assert 'password' not in str(events)
    assert 'Confidential' not in str(events)


@pytest.mark.parametrize('bad', ['x' * 130, 'key=Bearer xyz', 'tool\nname', '{unsafe}', '', 42.1])
def test_reject_untrusted_labels(bad):
    assert safe_label(bad) == 'unclassified'


def test_duration_and_event_limits():
    events = sanitize_tool_events([{'name': 'find_customer', 'duration_ms': -1,
                                    'status': 'ok'}] * 100)
    assert len(events) == 80
    assert all(e['duration_ms'] == 0 for e in events)


def test_no_evidence_from_untrusted_types():
    assert safe_evidence_refs({'fake': 'evidence'}) == []
    assert safe_evidence_refs(['customer:1', 'bad phrase', 123]) == ['customer:1']


def test_observability_migration_contains_owner_scoped_tables():
    content = (ROOT/'database/migrations/versions/0004_observability.py').read_text()
    for string in ['agent_runs', 'agent_tool_events', 'owner_sub',
                   'trace_id', 'ix_agent_runs_owner_time', 'uq_tool_event_run_order']:
        assert string in content


def test_observability_endpoints_require_authenticated_owner():
    main = (ROOT/'app/main.py').read_text()
    for string in ['/api/activity/summary', '/api/activity/runs',
                   '/api/activity/runs/{run_id}', 'auth.principal.sub']:
        assert string in main
    assert 'require_csrf(request, auth)' in main
    assert 'X-Request-ID' in main
    store = (ROOT/'app/telemetry/store.py').read_text()
    assert 'WHERE id=%s AND owner_sub=%s' in store
    assert 'FROM agent_runs WHERE owner_sub=%s' in store


def test_dashboard_does_not_use_html_injection():
    js = (ROOT/'app/static/workspace.js').read_text()
    assert 'innerHTML' not in js
    for component in ['loadActivity', 'loadRunDetails', 'activity-summary', 'activity-runs']:
        assert component in js or component in (ROOT/'app/templates/workspace.html').read_text()


def test_github_ci_actions_avoid_secrets_and_mutable_permissions():
    ci = (ROOT/'.github/workflows/ci.yml').read_text()
    live = (ROOT/'.github/workflows/integration.yml').read_text()
    assert 'contents: read' in ci and 'contents: read' in live
    assert 'workflow_dispatch' in live
    assert 'scripts/verify_static.sh' in ci
    assert 'app.telemetry.smoke_w11' in live
    assert 'docker compose up --build -d' in live
    assert 'actions/upload-artifact' in live


class FakeCursor:
    def __init__(self, db): self.db=db
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params):
        self.db.queries.append((sql, params))
        self.db.last_sql = sql
        self.db.last_params = params
        return self
    def fetchone(self):
        if 'owner_sub=%s' in self.db.last_sql and self.db.last_params[-1] != 'alice':
            return None
        if 'RETURNING id' in self.db.last_sql:
            return (uuid.uuid4(),)
        if 'SELECT id, conversation_id' in self.db.last_sql:
            return {'id':uuid.uuid4(), 'status':'complete'}
        if 'count(*)' in self.db.last_sql:
            return {'total_runs':1}
        return None
    def fetchall(self): return []


class FakeDB(FakeCursor):
    def __init__(self): self.queries=[]; self.db=self
    def cursor(self): return FakeCursor(self)
    def __enter__(self): return self
    def __exit__(self, *args): return None


def test_db_run_owner_is_checked_atomically(monkeypatch):
    from app.telemetry import store
    db = FakeDB()
    monkeypatch.setenv('DATABASE_URL','postgresql://unit-test')
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda *a, **k: db))
    r = store.create_run(conversation_id=uuid.uuid4(), owner_sub='alice', role='sales_user',
                         blueprint_version='1.0', model_name='qwen2.5:3b')
    assert r['trace_id']
    sql,params = db.queries[0]
    assert 'FROM conversations WHERE id=%s AND owner_sub=%s' in sql
    assert params[-1] == 'alice'
    with pytest.raises(PermissionError):
        store.create_run(conversation_id=uuid.uuid4(), owner_sub='bob',role='sales_user',
                         blueprint_version='1.0',model_name='qwen2.5:3b')


def test_db_run_telemetry_stays_without_prompt_or_token(monkeypatch):
    from app.telemetry import store
    db = FakeDB()
    monkeypatch.setenv('DATABASE_URL','postgresql://unit-test')
    monkeypatch.setitem(sys.modules,'psycopg', SimpleNamespace(connect=lambda *a, **k: db))
    store.finish_run(run_id=uuid.uuid4(), owner_sub='alice', status='complete',
        duration_ms=12, tool_events=[{'name':'find_customer','status':'ok',
        'duration_ms':3,'arguments':{'access_token':'DO_NOT_STORE'}}], evidence_refs=[])
    assert all('DO_NOT_STORE' not in str(query) for query in db.queries)
    assert any('INSERT INTO agent_tool_events' in sql for sql,_ in db.queries)
