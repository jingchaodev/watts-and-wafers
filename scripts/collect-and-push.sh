#!/bin/bash
# Cron entrypoint: run collectors for a group, commit data, push (pull-rebase first).
# Usage: collect-and-push.sh hourly|daily
set -uo pipefail
GROUP=${1:?usage: collect-and-push.sh hourly|daily}
REPO=/root/watts-and-wafers
LOG=$REPO/collect.log

cd "$REPO" || exit 1
{
  echo "--- $(date -u +%FT%TZ) group=$GROUP ---"
  python3 collectors/run.py --group "$GROUP"
  RC=$?
  if [[ $RC -ne 0 ]]; then
    echo "collectors failed rc=$RC — not pushing"
    exit $RC
  fi
  git add data/
  if git diff --cached --quiet; then
    echo "no data changes"
    exit 0
  fi
  git -c user.name="ww-collector" -c user.email="bot@watts-and-wafers" \
    commit -q -m "data: $GROUP $(date -u +%F' '%H:%M)"
  # pull-rebase before push: repo may have moved (manual edits, other host)
  git pull --rebase -q origin main || { echo "rebase failed"; exit 1; }
  git push -q origin main || { echo "push failed"; exit 1; }
  echo "pushed"
} >> "$LOG" 2>&1
# rotate log at 1MB
[[ $(stat -c%s "$LOG" 2>/dev/null || echo 0) -gt 1048576 ]] && tail -c 262144 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
