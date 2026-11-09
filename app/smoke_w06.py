"""Docker-only integration smoke for W06 conversation ownership using real Keycloak.

Browser OIDC/PKCE redirect and cookie CSRF must also be tested in a real browser.
"""
import asyncio
import uuid

import httpx2
from app.smoke import acquire

WEB = "http://web:8000"


async def main():
    alice = acquire("sales-demo", "SalesLocal2026!")
    bob = acquire("support-demo", "SupportLocal2026!")
    async with httpx2.AsyncClient(timeout=20) as client:
        me = await client.get(f"{WEB}/api/me", headers={"Authorization": f"Bearer {alice}"})
        assert me.status_code == 200 and me.json()["role"] == "sales_user", me.text
        assert "access_token" not in me.text
        response = await client.post(
            f"{WEB}/api/conversations", headers={"Authorization": f"Bearer {alice}"},
            json={"title": "Acme Retail investigation"},
        )
        assert response.status_code == 201, response.text
        cid = response.json()["id"]
        assert uuid.UUID(cid)
        mine = await client.get(f"{WEB}/api/conversations/{cid}",
                                headers={"Authorization": f"Bearer {alice}"})
        assert mine.status_code == 200 and mine.json()["messages"] == [], mine.text
        other = await client.get(f"{WEB}/api/conversations/{cid}",
                                 headers={"Authorization": f"Bearer {bob}"})
        assert other.status_code == 404, other.text
        other_list = await client.get(f"{WEB}/api/conversations",
                                      headers={"Authorization": f"Bearer {bob}"})
        assert cid not in str(other_list.json()), other_list.text
        noauth = await client.get(f"{WEB}/api/conversations")
        assert noauth.status_code == 401, noauth.text
        # The message endpoint is deliberately not simulated until W08.
        pending = await client.post(f"{WEB}/api/conversations/{cid}/messages",
                                    headers={"Authorization": f"Bearer {alice}"}, json={"message": "Hi"})
        assert pending.status_code == 501, pending.text
    print("LIVE_W06_OWNERSHIP_SMOKE_PASS")


if __name__ == "__main__":
    asyncio.run(main())
