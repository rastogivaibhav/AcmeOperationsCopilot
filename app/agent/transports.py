"""Runtime adapters for Ollama's native tool-calling API and authenticated MCP v2.

The core probe is transport-neutral for reliable offline tests.
"""
from __future__ import annotations

import json
import os
import re


class OllamaChat:
    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        self.url = (url or os.getenv("OLLAMA_URL", "http://ollama:11434")).rstrip("/")
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
        if not re.fullmatch(r"[1-9][0-9]{0,2}[smh]", self.keep_alive):
            raise ValueError("OLLAMA_KEEP_ALIVE_INVALID")
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
        if not 64 <= self.num_predict <= 1024:
            raise ValueError("OLLAMA_NUM_PREDICT_INVALID")

    async def check_model(self) -> dict:
        import httpx2
        async with httpx2.AsyncClient(timeout=20) as client:
            response = await client.get(self.url + "/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
        found = any(m.get("name") == self.model or m.get("model") == self.model for m in models)
        if not found:
            raise RuntimeError(f"OLLAMA_MODEL_NOT_PRESENT:{self.model}")
        return {"model": self.model, "installed": True}

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        import httpx2
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(15.0, read=240.0)) as client:
            response = await client.post(self.url + "/api/chat", json={
                "model": self.model, "messages": messages, "tools": tools,
                "stream": False, "keep_alive": self.keep_alive,
                "options": {"temperature": 0, "num_predict": self.num_predict},
            })
            response.raise_for_status()
            return response.json()


class AuthenticatedMCP:
    """One MCP connection per evaluation case. Credentials never sent to Ollama."""
    def __init__(self, access_token: str, url: str | None = None):
        if not access_token:
            raise ValueError("MCP bearer token required")
        self.token = access_token
        self.url = url or os.getenv("MCP_URL", "http://mcp:8001/mcp")
        self._http = None
        self._client = None
        self._http_ctx = None
        self._mcp_ctx = None

    async def __aenter__(self):
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        self._http_ctx = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=httpx2.Timeout(20.0, read=240.0))
        self._http = await self._http_ctx.__aenter__()
        try:
            self._mcp_ctx = Client(streamable_http_client(self.url, http_client=self._http))
            self._client = await self._mcp_ctx.__aenter__()
        except BaseException:
            await self._http_ctx.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._mcp_ctx is not None:
                await self._mcp_ctx.__aexit__(exc_type, exc, tb)
        finally:
            if self._http_ctx is not None:
                await self._http_ctx.__aexit__(exc_type, exc, tb)

    async def list_tools(self) -> list[dict]:
        result = await self._client.list_tools()
        return [t.model_dump(mode="json", by_alias=True) for t in result.tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        response = await self._client.call_tool(name, arguments)
        if response.is_error:
            return {"status": "tool_error", "error_code": "MCP_EXECUTION_ERROR", "evidence_refs": []}
        content = response.structured_content
        if isinstance(content, dict):
            # Official SDK may wrap the Python tool's return value in result.
            content = content.get("result", content)
        if not content and response.content:
            content = json.loads(response.content[0].text)
        if not isinstance(content, dict):
            raise ValueError("MCP_TOOL_RESULT_NOT_OBJECT")
        return content
