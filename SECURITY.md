# Security and responsible publication

This repository is a **local-only fictional case-study prototype**. It contains Keycloak *demo credentials* for repeatable offline assessment. They are not real secrets and must never be used on a publicly exposed service. Do not expose ports or deploy this configuration outside localhost.

- Keep actual credentials, private customer records, and token dumps out of commits. `.env` is ignored; `.env.example` has local defaults only.
- CI uses ephemeral services, deliberately fictitious records and repository read-only GitHub Actions permissions. Avoid uploading raw Compose logs as public artifacts because future logs could inadvertently contain business information.
- Do not use this system with real clients without TLS, dedicated production identity credentials, verified service-to-service delegation, production data access policies, secret management, data retention rules, threat modelling and operational hardening.
- Agent runs retain only limited identity-attributed metadata, durations, tool names, symbolic evidence references and error codes. Human business writes are separately attributed in the audit table.
- This work originated from a confidential recruitment assessment. **The assessment pack explicitly prohibits sharing the pack or solution during the assessment window.** GitHub Actions also runs on private repositories. Keep the repository private until publication is permitted.
- GitHub Actions code has not been run remotely in this authoring environment. Only unit and static checks have been performed here.
