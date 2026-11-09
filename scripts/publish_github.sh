#!/usr/bin/env bash
# Run on YOUR machine, after GitHub CLI authentication. Never prints a token.
set -euo pipefail
VISIBILITY="${1:---private}"
case "$VISIBILITY" in --private|--public) ;; *) echo 'Usage: publish_github.sh [--private|--public]' >&2; exit 2;; esac
OWNER="${GITHUB_OWNER:-rastogivaibhav}"
REPO="${GITHUB_REPO:-AcmeOperationsCopilot}"
if ! command -v gh >/dev/null 2>&1; then
  echo 'Install GitHub CLI: https://cli.github.com/ then run gh auth login' >&2; exit 1
fi
gh auth status >/dev/null
if [[ "$VISIBILITY" == '--public' ]]; then
  echo 'WARNING: The EY assessment instructions prohibit sharing the solution during the assessment window.' >&2
  echo 'Publishing publicly makes all source visible immediately. Continue only if disclosure is permitted.' >&2
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git init -b main; fi
git add --all
git diff --cached --quiet || git commit -m 'Acme Operations Copilot with observability and CI'
if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/$OWNER/$REPO.git"
  fi
  git push -u origin HEAD:main
else
  gh repo create "$OWNER/$REPO" "$VISIBILITY" --source . --remote origin --push
fi
echo "Published: https://github.com/$OWNER/$REPO"
