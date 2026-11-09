"""Transport-neutral execution tests: no LangGraph driver or live LLM required."""
import pytest

from app.agent.blueprint import load_blueprint
from app.agent.graph import execute_turn
from tests.test_w08_blueprints import TOOL_DEFINITIONS


class FakeMCP:
    async def list_tools(self):
        return TOOL_DEFINITIONS


class RecordingGraph:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def ainvoke(self, inputs, *, config, context):
        self.kwargs = {"inputs": inputs, "config": config, "context": context}
        return self.response


@pytest.mark.asyncio
async def test_execute_turn_uses_real_thread_id_and_per_run_context():
    graph = RecordingGraph({"status": "complete", "answer": "Found verified customer.",
                            "evidence_refs": ["customers:abc"], "tool_events": []})
    model = object()
    mcp = FakeMCP()
    out = await execute_turn(graph, "test-conversation", "Find customer", load_blueprint("sales_user"), model, mcp)
    assert out["status"] == "complete"
    assert graph.kwargs["config"]["configurable"]["thread_id"] == "conv:test-conversation"
    assert graph.kwargs["context"].model is model
    assert graph.kwargs["context"].mcp is mcp
    assert "access_token" not in str(graph.kwargs["config"])
    assert out["evidence_refs"] == ["customers:abc"]


@pytest.mark.asyncio
async def test_graph_does_not_pass_an_unexpected_final_state():
    graph = RecordingGraph({"status": "running", "answer": ""})
    with pytest.raises(ValueError, match="INVALID_GRAPH_FINAL_STATE"):
        await execute_turn(graph, "t", "Ask", load_blueprint("support_user"), object(), FakeMCP())
