#!/usr/bin/env sh
set -eu
python -m compileall -q app acme_shared mcp_server database evals tests
python -m pytest -q tests
python - <<'PY'
from pathlib import Path
import json, tomllib
root=Path('.')
json.loads((root/'infrastructure/keycloak/acme-realm.json').read_text())
tomllib.loads((root/'pyproject.toml').read_text())
print('JSON, TOML and Python compile checks PASSED')
PY
