"""Check evidence and packaging without pretending Docker integration was run.

Usage:
  python scripts/verify_release.py              # Offline readiness report, exits 0
  python scripts/verify_release.py --submission # Requires genuine live result files
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "W14-RELEASE-GATES.json"

MANDATORY = [
    "README.md", "ARCHITECTURE.md", "AI_USAGE.md", "SECURITY.md",
    "compose.yaml", "Dockerfile.web", "Dockerfile.mcp", ".env.example",
    ".github/workflows/ci.yml", ".github/workflows/integration.yml",
    "infrastructure/keycloak/acme-realm.json", "database/seed.py",
    "mcp_server/server.py", "app/main.py", "app/agent/graph.py",
    "app/skills/escalation.py", "app/telemetry/store.py",
    "docs/architecture.mmd", "evals/w13_cases.json", "evals/report.md",
    "evals/run_w13.py", "evals/w13_scoring.py", "tests/test_w13_evaluation.py",
]
CONFIDENTIAL_FILENAMES = ["FDE_Case Study_Candidate Pack.docx"]
LIVE_REPORTS = {
    "tool_routing": "evals/results/w07-live.json",
    "agent_graph": "evals/results/w08-live.json",
    "escalation_skill": "evals/results/w09-live.json",
    "write_controls": "evals/results/w10-live.json",
    "foundation": "evals/results/w11-live.json",
    "agent_evaluation": "evals/results/w13-live.json",
}


def inspect() -> dict:
    missing = [name for name in MANDATORY if not (ROOT/name).is_file()]
    leaks = [name for name in CONFIDENTIAL_FILENAMES if (ROOT/name).exists()]
    env = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('.env')
                 if '.venv' not in p.parts)
    design = json.loads((ROOT/'evals/w13_cases.json').read_text())
    ten_cases = len(design['cases']) == 10 and len({c['id'] for c in design['cases']}) == 10
    live = {}
    for key, filename in LIVE_REPORTS.items():
        path = ROOT / filename
        if not path.exists():
            live[key] = "not_run"
            continue
        try:
            data = json.loads(path.read_text())
            if key == "agent_evaluation":
                verified = data.get("live_runtime_verified") is True
                all_pass = data.get("summary", {}).get("passed") == 10
            elif key == "tool_routing":
                verified = data.get("live_runtime_verified") is True
                all_pass = (data.get("total") == 5 and data.get("passed") == 5
                            and len(data.get("evaluated_cases", [])) == 5)
            elif key == "escalation_skill":
                verified = data.get("verified") is True
                all_pass = (data.get("direct_skill_passed") is True and
                            data.get("model_selected_skill_passed") is True)
            else:
                verified = data.get("verified") is True
                all_pass = verified
            live[key] = "pass" if verified and all_pass else "failed_or_incomplete"
        except (OSError, ValueError):
            live[key] = "invalid_report"
    return {
        "status": ("source_checks_failed" if missing or leaks or env or not ten_cases
                   else "source_ready_live_verified" if all(v == "pass" for v in live.values())
                   else "source_ready_live_unverified"),
        "required_file_count": len(MANDATORY), "missing_required_files": missing,
        "confidential_documents_in_repo": leaks, "untracked_env_files_present": env,
        "ten_unique_evaluation_questions": ten_cases, "live_gates": live,
        "github_repository_published": "unverified",
        "docker_image_build": "unverified",
        "publication_restriction": "keep private during candidate assessment window",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--submission', action='store_true')
    args = p.parse_args()
    result = inspect()
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result['status'] == 'source_checks_failed':
        return 1
    if args.submission and any(v != 'pass' for v in result['live_gates'].values()):
        print('NOT_SUBMISSION_VERIFIED: live results missing or failed')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
