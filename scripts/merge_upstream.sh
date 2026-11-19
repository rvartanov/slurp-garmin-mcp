#!/usr/bin/env bash
# Merge new upstream commits (Taxuspt/garmin_mcp) into main through a pull request,
# but only when the merge is clean and the full test suite passes.
#
# Run from a checkout of main with the upstream remote fetched:
#   git fetch upstream main && scripts/merge_upstream.sh            # needs gh + GH_TOKEN
#   DRY_RUN=1 scripts/merge_upstream.sh                             # merge + test, push nothing
#
# Outcome (printed, and as "result=<value>" in $GITHUB_OUTPUT when set):
#   up_to_date   nothing to merge
#   merged       PR opened and merged
#   conflict     merge has conflicts; left to a person (see the upstream-sync issue)
#   tests_failed merge is clean but tests or generated files fail; left to a person
#   dry_run      merge and tests passed; nothing pushed
set -euo pipefail

UPSTREAM_REF="${UPSTREAM_REF:-upstream/main}"
BASE_BRANCH="${BASE_BRANCH:-main}"
UPSTREAM_REPO="${UPSTREAM_REPO:-Taxuspt/garmin_mcp}"
DRY_RUN="${DRY_RUN:-}"

out() {
    echo "$1"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "result=$1" >>"$GITHUB_OUTPUT"; fi
}

upstream_head="$(git rev-parse --verify "${UPSTREAM_REF}^{commit}")"
if [ "$(git rev-list --count "HEAD..${upstream_head}")" -eq 0 ]; then
    out up_to_date
    exit 0
fi

branch="upstream-sync/${upstream_head:0:7}"
git switch -q -C "$branch"
git -c user.name="slurp-upstream-bot" -c user.email="noreply@github.com" \
    merge --no-ff --no-edit -m "Merge upstream ${UPSTREAM_REPO}@${upstream_head:0:7}" "$upstream_head" >/dev/null 2>&1 || {
    git merge --abort 2>/dev/null || true
    git switch -q "$BASE_BRANCH"
    out conflict
    exit 0
}

# Generated tool lists must follow the merged code; regenerate and fold them
# into the merge commit so CI's up-to-date check passes.
if ! { uv sync -q && uv run -q python scripts/generate_tools_doc.py >/dev/null \
       && uv run -q python scripts/generate_dxt_tools.py >/dev/null \
       && uv run -q pytest -q tests/unit tests/integration; }; then
    git switch -q "$BASE_BRANCH"
    out tests_failed
    exit 0
fi
if [ -n "$(git status --porcelain docs/tools.md dxt/manifest.json)" ]; then
    git add docs/tools.md dxt/manifest.json
    git -c user.name="slurp-upstream-bot" -c user.email="noreply@github.com" commit -q --amend --no-edit
fi

if [ -n "$DRY_RUN" ]; then
    git switch -q "$BASE_BRANCH"
    out dry_run
    exit 0
fi

count="$(git rev-list --count "${BASE_BRANCH}..${upstream_head}")"
git push -q -f origin "$branch"
body="Merges ${count} commit(s) from \`${UPSTREAM_REPO}\` up to [\`${upstream_head:0:7}\`](https://github.com/${UPSTREAM_REPO}/commit/${upstream_head}).

The merge was clean and the full unit and integration test suite passed in the upstream-watch workflow; generated tool lists were refreshed. Merged automatically."
pr="$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty')"
if [ -z "$pr" ]; then
    gh pr create --base "$BASE_BRANCH" --head "$branch" --label upstream-sync \
        --title "Merge upstream ${UPSTREAM_REPO}@${upstream_head:0:7}" --body "$body" >/dev/null
    pr="$(gh pr list --head "$branch" --state open --json number --jq '.[0].number')"
fi
gh pr merge "$pr" --merge --delete-branch
git switch -q "$BASE_BRANCH"
out merged
