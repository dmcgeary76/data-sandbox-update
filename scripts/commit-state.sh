#!/usr/bin/env bash
# Commit changes under state/ and push, retrying if another job pushed first.
set -euo pipefail
msg="$1"
branch="${GITHUB_REF_NAME:-main}"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add state
if git diff --cached --quiet; then
  echo "No state changes to commit."
  exit 0
fi
git commit -q -m "$msg"
for i in 1 2 3 4; do
  if git pull -q --rebase origin "$branch" && git push -q origin "HEAD:$branch"; then
    echo "Committed: $msg"
    exit 0
  fi
  sleep $((i * 5))
done
echo "Could not push state after 4 attempts" >&2
exit 1
