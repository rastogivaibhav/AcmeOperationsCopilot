# W10 — Identity-authorised, confirmed business writes

**Date:** 2026-11-09
**State:** Source implementation and offline verification complete; actual Docker/Keycloak/MCP/PostgreSQL integration remains **UNVERIFIED**.

## Business outcome and scope

Two operations are implemented without giving the language model authority to execute them:

1. **Support/Admin:** `update_issue_status(issue_id, new_status, expected_version, note, approval_id, operation_id)`; permission enforced at authenticated MCP boundary and by a verified browser BFF. PostgreSQL enforces optimistic versioning and allowed state transitions; the transaction also writes `issue_updates`, immutable `issue_status_operations` receipt, and audit event.
2. **Admin:** `create_next_action(issue_id, description, approval_id, operation_id)`; existing W05 tool was tightened to require an explicitly confirmed, unexpired approval. The same operation ID returns the existing committed action on retry.

The model can select **local proposal tools** (`request_issue_update`, `request_next_action`) that return an advisory payload with `approval_required`. The proposed action is returned in the browser response, pre-filling the user-visible Action Centre. **Neither local tool calls the write-capable MCP tool or mints approval IDs.** Sales receives no write proposal tools. Support can propose an issue status update, and Admin can also propose a next-action record. Tool visibility is defined in versioned role blueprints and independently checked in Python.

## Two-phase authenticated UX

1. Authenticated user reviews the agent's proposed fields or manually enters a valid issue UUID, status + version + reason, or a next-action description.
2. `POST /api/actions/prepare` validates the current role and issue/version/transition, optionally checks conversation ownership, and creates a ten-minute **unconfirmed** database approval record with a server-generated unique `operation_id`. No business write occurs.
3. The user sees exact stored fields and clicks **Confirm and execute**.
4. `POST /api/actions/{approval_id}/confirm` requires explicit `{ "confirmed": true }`, CSRF protection for browser sessions, and current actor/role verification. It loads **stored** fields, not replacement fields from the request; records human confirmation and invokes the authenticated MCP operation.
5. MCP independently rechecks the Keycloak role and a bound approval; the database applies the write transaction and returns an attributable receipt. A network timeout after a successful commit can be reconciled by repeating confirmation with the **same operation ID**.
6. Unconfirmed approvals can be cancelled with `DELETE /api/actions/{approval_id}`. A confirmed or consumed approval cannot be cancelled; completed business changes would require a separate authorised compensating action.

**Important distinction:** the agent proposes; the browser-confirmed, current-identity backend executes. The LLM never receives approval IDs, operation IDs or raw access tokens.

## Data contracts

Migration `0003_controlled_writes` extends `approval_requests` with `kind`, `new_status`, `expected_version`, `note`, `confirmed_at`, and creates `issue_status_operations` with a unique primary key on `operation_id` and a reference to the new issue history row. Existing next-action approval rows with null `confirmed_at` cannot be used until reauthorised. Existing `POST /api/approvals` is retained for compatibility but now explicitly records confirmation when `confirmed=true`.

### Issue update transition policy (demo)

| Original | Allowed next |
|---|---|
| open | investigating, resolved |
| investigating | open, resolved |
| resolved | closed, investigating |
| closed | none |

Invalid transitions or stale `issues.version` result in 409 at preparation or commit. This transition policy is a **case-study assumption**, not specified by EY.

### New public endpoints

| Method | Route | Role | Outcome |
|---|---|---|---|
| POST | `/api/actions/prepare` | Support/Admin, according to intent | Pending approval receipt, no write |
| POST | `/api/actions/{approval_id}/confirm` | Original actor, current role | MCP-verified commit receipt |
| DELETE | `/api/actions/{approval_id}` | Original actor | Cancel unconfirmed approval |

Browser uses verified opaque session cookie and CSRF token. Tests can also use a verified Keycloak bearer token, which does not rely on browser cookies.

## Acceptance tests

Offline verification: `python -m pytest -q`, Python compilation, browser JS syntax. This checks validation, role profiles, proposal-only graph dispatch, actor binding, approval cancellation, transition and version failures, in-process simulated SQL execution, retry idempotency and code contracts. **These are not live database tests.**

### Required live gate (destructive to demo state)

```bash
cp -n .env.example .env
docker compose up --build -d
docker compose exec web python -m app.smoke
docker compose exec web python -m app.smoke_w10
docker compose cp web:/code/evals/results/w10-live.json ./evals/results/w10-live.json
```

`app.smoke_w10` uses real Keycloak tokens, browser API, MCP calls and PostgreSQL records to check:
- Sales issue update denied; Support next-action creation denied;
- Admin prepare does **not** write, and other users cannot confirm;
- Explicit confirmation is mandatory; admin next-action commit receives receipt;
- Admin retry returns same record and a single database row;
- Support issue status updates once, increments version and writes a history row;
- Support retry receives same update receipt;
- Stale issue version is rejected.

The smoke test mutates fictional seed data, and can be rerun: it picks a legal transition based on the current status of the selected demo issue. It produces a JSON report with `verified=true` **only after actual success**. The authoring environment does not have a Docker daemon, and no such passing report exists yet.

## Risks and deliberately deferred work

- A browser refresh can leave an unconfirmed approval stranded until expiry; restoring outstanding proposals and advanced interrupted-node recovery remain W16. Model proposal text is stored in graph checkpoints but is not yet separately indexed in an Activity Centre.
- Denied-operation audit details, OpenTelemetry spans, systematic token-cost measurement and dashboards are W12. Successful writes already record a durable `audit_events` row.
- The prototype gives Support/Admin global customer read/write scope; a real organisation must model team/customer scope per actor and verify it on every tool call.
- The separate confirmation is a user gesture plus an expiring DB record, not a cryptographically signed step-up MFA token.
- The current local Keycloak token has both web and MCP audiences; production systems should use properly scoped delegation/token exchange.
- The runtime has not been tested against the pinned official SDKs in a running environment. Do not claim EY-ready functionality until live acceptance succeeds.

## Next package

W11/W12: strengthen the webpage's business workflow and implement attributable structured traces, latency measurements, denied-operation auditing and evaluation evidence; then W13/W14 final end-to-end checks and submission packaging.
