#!/bin/bash
# Stage 1, agent arm. Drives a coding-agent CLI rather than a chat model.
#
# The difference matters. A chat model returns a message; an agent works in a
# directory and leaves files behind. The artefact under analysis is therefore
# stdout *plus* whatever it wrote, concatenated, because an Article 50 disclosure
# could land in either.
#
#   ./run_agent_cli.sh claude-code 'claude -p --permission-mode acceptEdits --tools Write,Edit,Read'
#
# Each prompt runs in its own scratch directory so nothing leaks between them.
#
# On permissions: the agent needs to be allowed to write files, or it stops and
# asks. It is deliberately NOT given Bash or network access. It runs in a throwaway
# directory with file tools only. That is a documentable deviation from how a
# developer would run it, and it is the safe end of the trade.
set -u

LABEL="${1:?usage: run_agent_cli.sh <label> <agent-command>}"
AGENT="${2:?usage: run_agent_cli.sh <label> <agent-command>}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/outputs/$LABEL"
WORKROOT="$(mktemp -d)"
mkdir -p "$OUT"

trap 'rm -rf "$WORKROOT"' EXIT

python3 - "$HERE" <<'PY' > "$WORKROOT/prompts.tsv"
import sys, yaml
for p in yaml.safe_load(open(sys.argv[1] + "/prompts.yaml")):
    print(p["id"] + "\t" + " ".join(p["prompt"].split()))
PY

while IFS=$'\t' read -r id prompt; do
  [ -s "$OUT/$id.md" ] && { echo "skip $id"; continue; }
  echo "generating $id ..."
  work="$WORKROOT/$id"
  mkdir -p "$work"
  (
    cd "$work" || exit 1
    printf '%s\n' "$prompt" | eval "$AGENT" > stdout.txt 2> stderr.txt
  )
  {
    echo "===== STDOUT ====="
    cat "$work/stdout.txt" 2>/dev/null
    # Anything the agent left on disk is part of the artefact.
    find "$work" -type f ! -name 'stdout.txt' ! -name 'stderr.txt' -size -256k 2>/dev/null \
      | sort | while read -r f; do
          echo ""
          echo "===== FILE: ${f#$work/} ====="
          cat "$f"
        done
  } > "$OUT/$id.md"
  bytes=$(wc -c < "$OUT/$id.md" | tr -d ' ')
  files=$(find "$work" -type f ! -name 'stdout.txt' ! -name 'stderr.txt' | wc -l | tr -d ' ')
  find "$work" -type f ! -name 'stdout.txt' ! -name 'stderr.txt' | sed "s|$work/||" | sort > "$OUT/$id.files.txt"
  echo "  ${bytes} bytes, ${files} file(s) written"
  if [ "$bytes" -lt 200 ]; then
    echo "  WARNING: near-empty. stderr was:"
    head -c 300 "$work/stderr.txt" 2>/dev/null | sed 's/^/    /'
  fi
done < "$WORKROOT/prompts.tsv"

echo ALLDONE
