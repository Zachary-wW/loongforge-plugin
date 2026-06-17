#!/usr/bin/env bash
# Re-freeze the witness baseline (sha + line count) from a given commit/branch.
# Run only when the witness is intentionally rebased onto a newer baseline.

set -euo pipefail

BRANCH="${1:-ai_v4}"
FILE="loongforge/models/foundation/deepseek_v4/deepseek_v4_attention.py"

cd "$(git rev-parse --show-toplevel)"

COMMIT="$(git rev-parse "$BRANCH")"
SHA256="$(git show "$BRANCH:$FILE" | shasum -a 256 | awk '{print $1}')"
LINES="$(git show "$BRANCH:$FILE" | wc -l | tr -d ' ')"

cat <<EOF
# Update README.md and expected_perf_findings.yml with:
branch       : $BRANCH
commit       : $COMMIT
file         : $FILE
file_sha256  : $SHA256
line_count   : $LINES
EOF
