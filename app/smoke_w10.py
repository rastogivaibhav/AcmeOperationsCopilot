"""Live W10 acceptance: authenticated API + MCP -> PostgreSQL (mutates fictional demo data).

Run ONLY on the disposable assessment Compose stack:
    docker compose exec web python -m app.smoke_w10
The check reports observed results, never simulated passes.
"""
import asyncio
import json
from pathlib import Path
import os
import sys
import uuid

import httpx2
import psycopg
from app.smoke import acquire, tool_call

ROOT = "http://web:8000"
ISSUE = "ab000000-0000-4000-8000-000000000002"
REPORT = Path("/code/evals/results/w10-live.json")


async def main():
    report = {"test": "W10", "verified": False, "checks": []}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    def checked(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    try:
        sales = acquire("sales-demo", "SalesLocal2026!")
        support = acquire("support-demo", "SupportLocal2026!")
        admin = acquire("admin-demo", "AdminLocal2026!")
        def headers(token):
            return {"Authorization": "Bearer " + token}
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(20.0, read=120.0)) as http:
            data = {"intent": {"kind": "issue_update", "issue_id": ISSUE,
                               "new_status": "investigating", "expected_version": 1,
                               "note": "Smoke test"}}
            r = await http.post(ROOT+"/api/actions/prepare", headers=headers(sales), json=data)
            checked("sales_update_denied", r.status_code == 403)
            r = await http.post(ROOT+"/api/actions/prepare", headers=headers(support), json={
                "intent": {"kind": "next_action", "issue_id": ISSUE,
                           "description": "Not allowed for support"}})
            checked("support_next_action_denied", r.status_code == 403)

            r = await http.post(ROOT+"/api/actions/prepare", headers=headers(admin), json={
                "intent": {"kind": "next_action", "issue_id": ISSUE,
                           "description": "W10 live evaluation: confirm next steps with account owner"}})
            checked("admin_next_action_prepared", r.status_code == 201)
            prepared = r.json()
            with psycopg.connect(os.environ["DATABASE_URL"]) as db:
                n = db.execute("SELECT count(*) FROM next_actions WHERE operation_id=%s",
                               (prepared["operation_id"],)).fetchone()[0]
            checked("prepare_did_not_write", n == 0)
            r = await http.post(ROOT+f"/api/actions/{prepared['approval_id']}/confirm",
                                headers=headers(support), json={"confirmed": True})
            checked("other_user_cannot_confirm", r.status_code == 404)
            r = await http.post(ROOT+f"/api/actions/{prepared['approval_id']}/confirm",
                                headers=headers(admin), json={"confirmed": False})
            checked("explicit_confirmation_required", r.status_code == 422)
            r = await http.post(ROOT+f"/api/actions/{prepared['approval_id']}/confirm",
                                headers=headers(admin), json={"confirmed": True})
            checked("admin_commit_success", r.status_code == 200 and
                    r.json().get("status") == "committed")
            receipt = r.json()
            again = await http.post(ROOT+f"/api/actions/{prepared['approval_id']}/confirm",
                                    headers=headers(admin), json={"confirmed": True})
            checked("admin_retry_same_receipt", again.status_code == 200 and
                    again.json()["receipt"]["id"] == receipt["receipt"]["id"])
            with psycopg.connect(os.environ["DATABASE_URL"]) as db:
                n = db.execute("SELECT count(*) FROM next_actions WHERE operation_id=%s",
                               (prepared["operation_id"],)).fetchone()[0]
            checked("admin_idempotency_single_row", n == 1)

            history = await tool_call(support, "get_issue_history", {"issue_id": ISSUE})
            checked("issue_history_available", history["status"] == "ok")
            old = history["data"]["issue"]
            old_status = old["status"]
            destination = {"open": "investigating", "investigating": "open",
                           "resolved": "investigating"}.get(old_status)
            if destination is None:
                raise AssertionError("Selected demo issue is closed; cannot perform transition")
            r = await http.post(ROOT+"/api/actions/prepare", headers=headers(support), json={
                "intent": {"kind": "issue_update", "issue_id": ISSUE,
                           "new_status": destination, "expected_version": old["version"],
                           "note": "W10 live test: status transition confirmed by support user"}})
            checked("support_issue_update_prepared", r.status_code == 201)
            planned = r.json()
            r = await http.post(ROOT+f"/api/actions/{planned['approval_id']}/confirm",
                                headers=headers(support), json={"confirmed": True})
            checked("support_issue_status_committed", r.status_code == 200 and
                    r.json().get("status") == "committed")
            update_receipt = r.json()["receipt"]
            replay = await http.post(ROOT+f"/api/actions/{planned['approval_id']}/confirm",
                                     headers=headers(support), json={"confirmed": True})
            checked("issue_retry_same_receipt", replay.status_code == 200 and
                    replay.json()["receipt"]["update_id"] == update_receipt["update_id"])
            current = await tool_call(support, "get_issue_history", {"issue_id": ISSUE})
            checked("issue_version_incremented", current["data"]["issue"]["version"] == old["version"]+1)
            checked("issue_status_changed", current["data"]["issue"]["status"] == destination)
            r = await http.post(ROOT+"/api/actions/prepare", headers=headers(support), json={
                "intent": {"kind": "issue_update", "issue_id": ISSUE,
                           "new_status": old_status, "expected_version": old["version"],
                           "note": "Stale request must be rejected"}})
            checked("stale_version_rejected", r.status_code == 409)
        report["verified"] = True
    except Exception as exc:
        report["error_class"] = type(exc).__name__
        report["verified"] = False
    finally:
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["verified"]:
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    print("LIVE_W10_WRITE_GATES_PASS")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
