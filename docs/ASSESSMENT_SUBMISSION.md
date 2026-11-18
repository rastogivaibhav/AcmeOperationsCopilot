# EY FDE case study — submission manifest and reviewer guide

**Prepared 18 November 2026** · **Repository:** [Acme Operations Copilot](https://github.com/rastogivaibhav/AcmeOperationsCopilot) · **Visibility:** private · **Default branch:** \`main\`

This manifest maps the five explicitly requested items in Section 5 of the candidate brief to artefacts a reviewer can open. The submission clock in the brief is **48 hours after receipt**; the actual receipt time and any deadline extension must be confirmed by the candidate/recruiter. Do not silently assume a new deadline.

## The five deliverables — exact locations

| # | Brief requirement | What to send / where to find it | Status |
|---|---|---|---|
| 1 | **GitHub repository access or ZIP of code and configuration** | Private [GitHub repository](https://github.com/rastogivaibhav/AcmeOperationsCopilot) → \`main\` including \`compose.yaml\`, \`Dockerfile.web\`, \`Dockerfile.mcp\`, \`.env.example\`, migrations, app, MCP, tests and CI. Alternative: in GitHub select **Code → Download ZIP**, or use \`git archive\` after authenticating locally. | Code complete; **EY access must be granted or a ZIP actually sent by candidate** |
| 2 | **README — setup, architecture, trade-offs, AI usage** | [README.md](../README.md), with [security limits](../SECURITY.md), [architecture](../ARCHITECTURE.md), [AI-usage disclosure](../AI_USAGE.md). | Supplied in repository |
| 3 | **System architecture diagram — components and data flows** | [Current architecture narrative](architecture-review.md) with rendered Mermaid diagrams, plus standalone [diagram source](architecture-current.mmd). | Supplied in repository |
| 4 | **Evaluation output with commentary** | [Latest measured evidence and case-level observations](../evals/EVIDENCE_MAIN.md), [evaluation report](../evals/report.md), tests \`evals/w13_cases.json\` / \`evals/run_w13.py\`. Raw run output: [GitHub Actions integration run 42986664790](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664790) → artifact \`acme-live-evaluation\`. | **206 tests, W07 5/5, W13 10/10**, structural gates; manual semantic adjudication not represented as complete |
| 5 | **AI usage notes — brief written account of AI tools** | [AI_USAGE.md](../AI_USAGE.md), with a dedicated answer to **each of the four panel questions** and the actual debugging chronology. | Supplied; candidate should personally review and stand behind it |

## Access and submission actions still owned by the candidate

- [ ] Confirm the **48-hour deadline**, permitted mode of submission and permitted repository sharing with the recruiter.
- [ ] Identify authorised EY reviewer GitHub usernames; invite **read-only** reviewers in **Settings → Collaborators / Manage access**. The repository URL by itself **will not grant access**.
- [ ] If reviewers cannot authenticate to private GitHub, send the **source ZIP** through the recruiter-approved secure channel instead. The source archive is **not** the GitHub Actions evidence ZIP.
- [ ] Verify the reviewer can open source, README, architecture, evaluation evidence and AI-usage document.
- [ ] Personally review \`AI_USAGE.md\`, the real run outputs and the code. Complete \`evals/manual_review_template.csv\` if a personal semantic review has actually been performed; **do not mark it complete on the strength of automated tests alone**.
- [ ] Confirm the confidential EY candidate pack and any genuine credentials/customer data were **not** included in the repository/ZIP. Keep the repository **private**.
- [ ] Send the repository link / approved ZIP and the five-item manifest before the agreed deadline.

## Ready-to-use short handover text

**Subject:** EY Applied AI Case Study — Acme Operations Copilot Submission

Please find my private Acme Operations Copilot repository here:
https://github.com/rastogivaibhav/AcmeOperationsCopilot

It contains the complete source and configuration, setup README, current architecture and data-flow diagrams, evaluation evidence with commentary, and AI-assistance disclosure. The reproducible Docker/Ollama/Keycloak/MCP integration and ten-case evaluation passed on the assessed \`main\` revision. I have also documented the prototype's limitations, including the distinction between automated structural acceptance and independent human review.

Please let me know which GitHub accounts should be granted access, or if a secure ZIP delivery is preferable.

## Evidence boundary and status

The last checked source revision is \`54442f2f5704676f563127fde0a7ab611016c3f1\`; [source CI](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664730) and [full integration](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42986664790) **both passed** on this exact SHA (11 November 2026). Subsequent documentation-only commits do not change those measured model outcomes; check their own CI.

- **Automated structural completion:** demonstrated for the defined ten W13 scenarios; no guarantee for unseen prompts, business advice quality or arbitrary customer configurations.
- **Security:** local fictional prototype only; Keycloak development realm, localhost HTTP and demo credentials are **not production controls**.
- **Human review:** explicit panel and candidate responsibility. No claim that the candidate personally executed each test or independently reviewed every generated statement.
