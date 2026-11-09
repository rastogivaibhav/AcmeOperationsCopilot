# W13/W14 implementation status

**Completed as source artifacts:** 9 November 2026.

## W13 — evaluation and evidence

- `evals/w13_cases.json`: exactly ten question cases, each independent, covering three authenticated roles, tool-selection, source references, lack of access, contradictory issue updates, role-specific write proposals and tool minimality.
- `evals/w13_scoring.py`: deterministic scorers for tool order, missing tool use, forbidden business writes, required evidence records, plausible extra identifiers, expected risk terms, proposal presence and no unsupported completion claim.
- `evals/run_w13.py`: real model + LangGraph + authenticated MCP evaluation runner; produces JSON and Markdown with measured latency and failure reasons. No mock evaluation results are substituted.
- `evals/report.md`: unmeasured-status documentation for the evaluator and explicit manual review requirements.
- `evals/manual_review_template.csv`: ten-row human factual-grounding/action reasonableness review worksheet, intentionally blank.
- `tests/test_w13_evaluation.py`: regression tests of evaluation rules.

## W14 — release and handover

- `docs/architecture.mmd`: full low-level data-flow and trust-boundary diagram.
- `docs/FINAL_SUBMISSION_CHECKLIST.md`: the five EY deliverables, live test instructions, GitHub Actions and 15-minute demo flow.
- `scripts/verify_release.py`: release manifest checking source, confidentiality guard and the required live evidence flags. `--submission` fails until live reported evidence is present and marked passed.
- Existing two GitHub Actions workflows now include W13; `ci.yml` checks the source manifest, `integration.yml` exercises live W13 and preserves output artifacts.
- `README.md` and `AI_USAGE.md` updated to distinguish actual measurements from design and unit tests.

## Verified here

- Existing W01–W12 offline test baseline: 142 pass.
- New W13 scoring and design tests: 13 pass.
- Combined: **155 offline tests pass**.
- Python compilation/JSON/YAML validity, JavaScript syntax and repository manifest checked.

## Not verified here

- No Docker daemon, GitHub Actions run or real model test performed here.
- No public or private GitHub repository created or updated; connector has no repository-creation action, and confidentiality calls for a private repository during the assessment window.
- The 10-case live metric, human recommendation review and real CI container-build outputs remain pending.
