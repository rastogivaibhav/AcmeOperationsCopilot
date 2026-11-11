# Security and responsible publication

**Private EY assessment prototype — not production software.** The repository contains only fictional demonstration customers and deliberately disposable Keycloak users/passwords so it can be tested offline. Those passwords are not real secrets and must **never** be reused or exposed on the public internet.

## Publication and access boundary

- Keep the repository **private** during EY's assessment/confidentiality window; do not publish the confidential assessment pack or the submitted solution publicly.
- Share access only with authorised EY panel members using their GitHub usernames (**Settings → Collaborators / Manage access → Add people**). A private GitHub URL alone does not give someone access.
- Do not commit actual business data, customer records, access tokens, browser sessions, API keys, credentials or private recruiting documents. \`.env\` should remain untracked; \`.env.example\` is for fictional local defaults.
- GitHub Actions uses ephemeral runners and read-only repository contents permissions; share only appropriately redacted evidence. Do not attach raw token dumps or unreviewed infrastructure logs.

## Technical boundaries and observed checks

- Keycloak/OIDC authenticates users; the web application and MCP server independently verify audience-scoped tokens and enforce role/customer permissions. A prompt or model-generated customer ID is **not** an authorisation grant.
- The model can request read-only Skills and advisory action proposals, **not** directly perform business writes. Actual writes require server-side role checks, a separately confirmed approval, audit receipts and operation-id idempotency.
- Browser CSRF and owner-scoped conversation checks have been exercised against the real Docker Compose stack. The completed [live integration run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42983299825) passed Keycloak/MCP, browser identity isolation, W07/W08/W09, W13 **10/10 structural checks**, fixture integrity and controlled-write smoke tests.
- Post-merge \`main\` CI passed on [run 42984994299](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994299); the separate [full-stack run 42984994525](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42984994525) must be assessed on its own result.
- Automated checks do **not** amount to a penetration test, proof against prompt injection or complete human validation of natural-language facts.

## Explicitly out of scope

The demo uses loopback HTTP, \`HttpOnly; SameSite=Lax\` cookies without the production \`Secure\` flag, a development-mode Keycloak realm, shared demo PostgreSQL infrastructure and local fictional users. Do not expose ports, enable public access, or use real customer data. A production version would need HTTPS, secret management, hardened identity delegation and token exchange, separate service credentials, threat modelling, retention/deletion controls, operational monitoring and independent security review.
