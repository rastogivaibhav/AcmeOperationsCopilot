# W13 Evaluation — measured baseline and adaptation branch

**Measured main-branch reference:** 10 November 2026, commit 47eb98b6689b13e16c7185aa123da126f0fd9185.

[GitHub Actions: verified baseline run](https://github.com/rastogivaibhav/AcmeOperationsCopilot/actions/runs/42858736570)

| Gate | Observed result |
|---|---|
| Automated source tests | 171 passed |
| Docker builds, Keycloak, MCP, browser OIDC and ownership | Passed |
| Controlled writes, role restrictions and W08 LangGraph | Passed |
| W07 tool routing | 3 / 5 |
| W09 direct authenticated Skill | Passed |
| W09 model-selected Skill | Failed |
| W13 ten-case structural assessment | 6 / 10 |
| Full-stack release acceptance | Failed |

The observed failures include wrong tool selection, missing customer resolution, unsuccessful action proposal, and two 150-second timeouts. The GitHub Actions artifact contains the recorded tool/event paths. No human semantic accuracy or recommendation-quality verdict has been completed.

## NVIDIA-inspired draft PR #1

The feature branch implements typed request signals, authenticated Skill/proposal prerequisites, fixture integrity checks, trajectory evaluation, and a fixed risk-assessment clock *only for automated evaluation*. See docs/NVIDIA_BLUEPRINT_ADAPTATION.md.

**These changes are not yet verified to improve live model performance.** Preserve all failure cases and compare the new run against the original with identical baseline fixtures, prompt/model settings and evaluation clock.

An automated PASS verifies measured structure and specified record references. It does not independently prove that each natural-language factual claim is correct. A human reviewer must assess contradictory updates, missing information, recommendations and unauthorised actions. Do not substitute unit tests for measured inference.
