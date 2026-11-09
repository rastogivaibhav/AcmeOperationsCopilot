"""Run from inside web container: docker compose exec web python -m app.smoke.

Exercises live Keycloak, API auth, MCP transport, DB and role isolation.
Uses disposable local demo credentials only; never print tokens.
"""
import asyncio
import json
import os
import sys
import uuid
import urllib.parse
import urllib.request

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

ID = "ac000000-0000-4000-8000-000000000001"
ISSUE = "ab000000-0000-4000-8000-000000000001"


def acquire(username, password):
    endpoint = "http://keycloak:8080/realms/acme/protocol/openid-connect/token"
    form = urllib.parse.urlencode({"grant_type": "password", "client_id": "acme-web",
                                   "username": username, "password": password}).encode()
    request = urllib.request.Request(endpoint, data=form)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["access_token"]


async def tool_call(token, name, arguments):
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"},
                                  timeout=httpx2.Timeout(20.0, read=90.0)) as http:
        async with Client(streamable_http_client("http://mcp:8001/mcp", http_client=http)) as session:
            response = await session.call_tool(name, arguments)
            if response.is_error:
                raise RuntimeError(f"MCP error calling {name}: {response}")
            raw = response.structured_content
            if raw and "result" in raw:
                raw = raw["result"]
            if not raw and response.content:
                raw = json.loads(response.content[0].text)
            return raw


async def main():
    for user, password in (("sales-demo", "SalesLocal2026!"),
                           ("support-demo", "SupportLocal2026!"),
                           ("admin-demo", "AdminLocal2026!")):
        token = acquire(user, password)
        async with httpx2.AsyncClient() as http:
            r = await http.get("http://web:8000/api/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"API auth failure: {r.status_code} {r.text}"
            print("IDENTITY_OK", user, r.json()["role"])
        result = await tool_call(token, "find_customer", {"customer_name": "Acme Retail"})
        assert result["status"] == "ok", result
        print("MCP_CUSTOMER_OK", user, result["data"]["id"])
        issues = await tool_call(token, "list_open_issues", {"customer_id": ID})
        assert issues["status"] == "ok" and issues["data"], issues
        history = await tool_call(token, "get_issue_history", {"issue_id": ISSUE})
        assert history["status"] == "ok", history
        denied = await tool_call(token, "create_next_action", {
            "issue_id": ISSUE, "description": "Probe access without approval",
            "approval_id": str(uuid.uuid4()), "operation_id": str(uuid.uuid4())
        })
        expected = "approval_required" if user == "admin-demo" else "forbidden"
        assert denied["status"] == expected, (user, denied)
        print("MCP_WRITE_GATE_OK", user, expected)
    sales = acquire("sales-demo", "SalesLocal2026!")
    out_of_scope = await tool_call(sales, "find_customer", {"customer_name": "Northstar Finance"})
    assert out_of_scope["status"] == "not_found", out_of_scope
    print("SCOPE_DENIAL_OK", out_of_scope["status"])
    print("LIVE_FOUNDATION_SMOKE_PASS")


if __name__ == "__main__":
    asyncio.run(main())
