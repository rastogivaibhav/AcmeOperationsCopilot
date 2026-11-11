# NVIDIA-inspired Acme Agent Workflow Adaptation

**Status:** Draft PR #1, not yet accepted on live model metrics. No NVIDIA runtime, hosted endpoint, or proprietary source code has been added.

## Design references

- [NVIDIA Multi-Agent Intelligent Warehouse](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse): typed procedures, validated prerequisites, human approval and outcome verification.
- [NVIDIA Deep Researcher / AI-Q](https://github.com/NVIDIA-AI-Blueprints/deep-researcher-agent): intent/evidence/reasoning separation.
- [NVIDIA NeMo Agent Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit): tool-trajectory measurement, performance profiling, evaluation provenance.

These are design-pattern adaptations. No NVIDIA SDK dependency or blueprint implementation code is copied.

## PR1: typed guidance and explicit issue references

- app/agent/intent.py extracts explicitly supplied issue IDs and bounded intent cues.
- app/agent/graph.py and app/agent/tool_probe.py provide hints while preserving model-selected tool choice.
- Wrong customer-lookups for unambiguous issue-history requests get validation feedback rather than retrieving invented customer names.
- A user ID is a reference, not an authorisation token: all reads remain scoped by MCP and Keycloak.
- Multiple entities are not silently disambiguated.

## PR2: authenticated Skills and proposal prerequisites

- app/skills/escalation.py accepts a customer ID or a name, resolving names via authenticated MCP.
- The audit adapter only permits find_customer, list_open_issues and get_issue_history.
- app/agent/dependencies.py requires an authoritative issue-history record, binds the current version, and verifies an allowed status transition before drafting an action.
- Prerequisite history retrieval is read-only, bounded, and marked separately from model-selected tools.
- The human prepare/confirm action flow, policy enforcement, idempotency and database writes are unchanged.

## PR3: reproducible evaluation and honest provenance

- evals/fixture_guard.py fingerprints customer/issue/update/action rows before and after the read-only agent tests. Reports store hashes/counts, not business content.
- The W10 mutation smoke follows the model evaluation, not precedes it.
- The W13 as-of clock is fixed only for the evaluation session, leaving real-user risk calculations unchanged.
- evals/trajectory.py distinguishes model-selected calls from policy and Skill dependencies, validates prerequisite order, and records invalid argument calls.
- W13 records distinct tool-trajectory checks and measured median/p95 case latencies; these cannot replace human review of semantic factual correctness.
- A strict submission release gate checks real W07/W08/W09/W10/W11/W13 reports, not merely source files.

## Pre-change evidence

Measured main-branch reference at commit 47eb98b on 10 November 2026:
- 171/171 offline tests and both Docker image builds passed.
- Keycloak/MCP, real browser session isolation, W08, role checks and controlled writes passed.
- W07 3/5, W09 model-selected Skill failed, W13 6/10; full live acceptance failed.

The feature branch must be rerun on the same dataset and clock before making improvement claims.
Goals: repeatable W07 5/5, W09 direct + model-selected Skill, W13 9/10+ (with case-level commentary), unchanged write denials, no fixture drift, and manual groundedness review.

## Deliberately excluded

No new LLM provider, GPU, NIM, vector database, multi-agent swarm, autonomous business writes, or public deployment. Fictional development credentials and HTTP loopback remain non-production.
