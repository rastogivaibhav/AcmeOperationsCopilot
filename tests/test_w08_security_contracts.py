from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def test_api_auth_checks_ownership_before_graph_execution():
    text = (BASE / "app/main.py").read_text()
    route = text.split('async def send_agent_message', 1)[1]
    assert route.index('conversations_store.get_owned') < route.index('execute_turn(')
    assert 'require_csrf(request, auth)' in route
    assert 'authenticated' in text
    assert 'Conversation is processing another request' in route
    assert 'Agent profile changed; start a new investigation' in route


def test_agent_token_is_only_runtime_context():
    graph = (BASE / "app/agent/graph.py").read_text()
    assert 'context=context' in graph
    assert '"access_token"' not in graph
    assert '"Authorization"' not in graph
    assert 'thread_id' in graph
    assert 'from langgraph.graph import' in graph


def test_browser_chat_escapes_untrusted_text():
    js = (BASE / "app/static/workspace.js").read_text()
    html = (BASE / "app/templates/workspace.html").read_text()
    assert 'innerHTML' not in js
    assert 'textContent' in js
    assert 'id="chat-form"' in html
    assert '/api/conversations/' in js


def test_postgres_checkpointer_created_on_app_lifespan():
    main = (BASE / "app/main.py").read_text()
    assert 'AsyncPostgresSaver.from_conn_string' in main
    assert 'await checkpointer.setup()' in main
    assert 'FastAPI(title=' in main and 'lifespan=lifespan' in main
