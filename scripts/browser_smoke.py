"""Browser-level Keycloak OIDC + role visibility + conversation ownership smoke.

Run from a host with Playwright/Chromium and the full Compose stack at localhost.
Uses only fictional demo accounts. Never logs cookies, tokens or credentials.
This is a functional acceptance smoke, not a security penetration test.
"""
from __future__ import annotations

import asyncio
import os
import re
import uuid

BASE = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")


async def sign_in(browser, username: str, password: str):
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    await page.locator("#username").fill(username, timeout=30000)
    await page.locator("#password").fill(password)
    await page.locator("#kc-login").click()
    await page.wait_for_url(re.compile(r"^http://(?:localhost|127\.0\.0\.1):8000/app"),
                            timeout=45000)
    await page.locator("#workspace").wait_for(timeout=20000)
    return context, page


async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            sales_context, sales = await sign_in(browser, "sales-demo", "SalesLocal2026!")
            assert "Sales User" in await sales.locator(".role-badge").inner_text()
            assert await sales.locator("#write-workflow").count() == 0
            await sales.locator("#title").fill("Browser ownership acceptance")
            await sales.locator("#new-conversation button[type=submit]").click()
            await sales.wait_for_url(re.compile(r"[?&]conversation=[0-9a-f-]{36}"), timeout=15000)
            conversation = await sales.evaluate("new URL(location.href).searchParams.get('conversation')")
            assert str(uuid.UUID(conversation)) == conversation
            await sales.reload(wait_until="domcontentloaded")
            await sales.locator("#chat-input:not([disabled])").wait_for(timeout=15000)
            assert "Browser ownership acceptance" in await sales.locator("#chat-title").inner_text()
            print("BROWSER_SALES_LOGIN_CONVERSATION_RESTORE_OK", flush=True)

            support_context, support = await sign_in(browser, "support-demo", "SupportLocal2026!")
            assert "Support User" in await support.locator(".role-badge").inner_text()
            assert await support.locator("#write-workflow").count() == 1
            response_status = await support.evaluate("""async (id) => {
                const response = await fetch('/api/conversations/' + id);
                return response.status;
            }""", conversation)
            assert response_status == 404
            print("BROWSER_SUPPORT_SCOPE_ISOLATION_OK", flush=True)
            await sales_context.close()
            await support_context.close()
        finally:
            await browser.close()
    print("BROWSER_OIDC_ACCEPTANCE_PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
