#!/usr/bin/env bash
# Starts this repo's GitHub workflows on time, from cron on a server you control.
#
# GitHub's own schedule is best-effort: in practice it starts each scheduled
# workflow about once a day, hours late. This script, run hourly by cron,
# starts the workflows through GitHub's API at the right Pacific times
# (the same as pressing "Run workflow" in the Actions tab).
#
# The workflows' own guards still decide what is due, so a duplicate start
# (this script plus GitHub's schedule) never runs drift twice or repeats a
# login batch. Keep the hours below in step with config/sandbox.yaml.
#
# Setup: see "Reliable scheduling from a server" in README.md.
set -euo pipefail

REPO="${SIM_REPO:-dmcgeary76/data-sandbox-update}"
TOKEN_FILE="${SIM_TOKEN_FILE:-/etc/sandbox-sim/github-token}"
DRIFT_HOUR_PT=5              # drift.run_hour_pt
LOGIN_HOURS_PT="8 10 12 14"  # logins.batch_hours_pt

# Pacific time, whatever the server's own timezone is.
hour=$(TZ=America/Los_Angeles date +%-H)
weekday=$(TZ=America/Los_Angeles date +%u)   # 1 = Monday ... 7 = Sunday
hour=${SIM_FAKE_HOUR:-$hour}                 # for testing only
weekday=${SIM_FAKE_WEEKDAY:-$weekday}

[ "$weekday" -le 5 ] || exit 0

dispatch() {
  local workflow=$1
  if [ -n "${SIM_DRY_RUN:-}" ]; then
    echo "$(date -Is) would start $workflow"
    return
  fi
  curl -fsS -X POST \
    -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$REPO/actions/workflows/$workflow/dispatches" \
    -d '{"ref":"main"}'
  echo "$(date -Is) started $workflow"
}

[ "$hour" -eq "$DRIFT_HOUR_PT" ] && dispatch drift.yml
for h in $LOGIN_HOURS_PT; do
  [ "$hour" -eq "$h" ] && dispatch logins.yml
done
exit 0
