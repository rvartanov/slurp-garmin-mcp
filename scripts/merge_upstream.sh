#!/usr/bin/env bash
# Prepare a merge of new upstream commits (Taxuspt/garmin_mcp) into main and
# offer it as a pull request for review. Nothing is merged automatically.
#
# The work is split in two so that upstream code never runs with a write token:
#
#   prepare  Merge upstream into a branch, refresh the generated tool lists and
#            run the unit and integration tests. This executes upstream code,
#            so run it without credentials (the upstream-watch "test" job has
#            only contents: read). When everything passes, the branch is
#            written to the git bundle $BUNDLE.
#   publish  Read the branch from $BUNDLE, check that it is the expected merge
#            commit, push it and open (or update) a pull request. It runs no
#            project code; it needs gh and GH_TOKEN.
#
# Run from a checkout of main with the upstream remote fetched:
#   git fetch upstream main && BUNDLE=/path/sync.bundle scripts/merge_upstream.sh prepare
#   BUNDLE=/path/sync.bundle scripts/merge_upstream.sh publish
#   DRY_RUN=1 scripts/merge_upstream.sh                   # merge + test, write and push nothing
#
# Outcome (printed, and as "result=<value>" in $GITHUB_OUTPUT when set):
#   up_to_date   nothing to merge
#   conflict     merge has conflicts; left to a person (see the upstream-sync issue)
#   tests_failed merge is clean but tests or generated files fail; left to a person
#   ready        merge and tests passed; branch written to $BUNDLE
#   dry_run      merge and tests passed; nothing written
#   pr_opened    publish: branch pushed, pull request open and waiting for review
set -euo pipefail

MODE="${1:-prepare}"
UPSTREAM_REF="${UPSTREAM_REF:-upstream/main}"
BASE_BRANCH="${BASE_BRANCH:-main}"
UPSTREAM_REPO="${UPSTREAM_REPO:-Taxuspt/garmin_mcp}"
DRY_RUN="${DRY_RUN:-}"
BUNDLE="${BUNDLE:-}"

out() {
    echo "$1"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "result=$1" >>"$GITHUB_OUTPUT"; fi
}

prepare() {
    local upstream_head base_head branch
    upstream_head="$(git rev-parse --verify "${UPSTREAM_REF}^{commit}")"
    base_head="$(git rev-parse --verify "HEAD^{commit}")"
    if [ "$(git rev-list --count "HEAD..${upstream_head}")" -eq 0 ]; then
        out up_to_date
        return 0
    fi
    if [ -z "$DRY_RUN" ] && [ -z "$BUNDLE" ]; then
        echo "prepare needs BUNDLE=<file> (or DRY_RUN=1)" >&2
        return 2
    fi

    branch="upstream-sync/${upstream_head:0:7}"
    git switch -q -C "$branch"
    git -c user.name="slurp-upstream-bot" -c user.email="noreply@github.com" \
        merge --no-ff --no-edit -m "Merge upstream ${UPSTREAM_REPO}@${upstream_head:0:7}" "$upstream_head" >/dev/null 2>&1 || {
        git merge --abort 2>/dev/null || true
        git switch -q "$BASE_BRANCH"
        out conflict
        return 0
    }

    # Generated tool lists must follow the merged code; regenerate and fold them
    # into the merge commit so CI's up-to-date check passes.
    if ! { uv sync -q && uv run -q python scripts/generate_tools_doc.py >/dev/null \
           && uv run -q python scripts/generate_dxt_tools.py >/dev/null \
           && uv run -q pytest -q tests/unit tests/integration; }; then
        git switch -q -f "$BASE_BRANCH"
        out tests_failed
        return 0
    fi
    if [ -n "$(git status --porcelain docs/tools.md dxt/manifest.json)" ]; then
        git add docs/tools.md dxt/manifest.json
        git -c user.name="slurp-upstream-bot" -c user.email="noreply@github.com" commit -q --amend --no-edit
    fi

    if [ -n "$DRY_RUN" ]; then
        git switch -q -f "$BASE_BRANCH"
        out dry_run
        return 0
    fi

    # Only the new commits; publish already has main and upstream.
    git bundle create -q "$BUNDLE" "$branch" "^${base_head}" "^${upstream_head}"
    git switch -q -f "$BASE_BRANCH"
    out ready
}

publish() {
    local heads ref tip upstream_head branch parents count body pr
    if [ -z "$BUNDLE" ] || [ ! -f "$BUNDLE" ]; then
        echo "publish needs BUNDLE=<file> written by prepare" >&2
        return 2
    fi
    git bundle verify -q "$BUNDLE" >/dev/null 2>&1 || { echo "invalid bundle: $BUNDLE" >&2; return 1; }

    # The bundle comes from a job that ran upstream code: trust nothing in it
    # beyond what is checked here, and let a person review the result.
    heads="$(git bundle list-heads "$BUNDLE")"
    if [ "$(printf '%s\n' "$heads" | wc -l)" -ne 1 ]; then
        echo "bundle must hold exactly one branch" >&2
        return 1
    fi
    ref="${heads#* }"
    if ! [[ "$ref" =~ ^refs/heads/upstream-sync/[0-9a-f]{7}$ ]]; then
        echo "unexpected branch in bundle: $ref" >&2
        return 1
    fi
    branch="${ref#refs/heads/}"
    git fetch -q --no-tags "$BUNDLE" "+${ref}:refs/upstream-sync/candidate"
    tip="$(git rev-parse --verify "refs/upstream-sync/candidate^{commit}")"

    upstream_head="$(git rev-parse --verify "${UPSTREAM_REF}^{commit}")"
    parents="$(git rev-list --parents -n 1 "$tip")"
    read -r _ first second extra <<<"$parents"
    if [ -n "${extra:-}" ] || [ -z "${second:-}" ] || [ "$second" != "$upstream_head" ] \
        || [ "upstream-sync/${upstream_head:0:7}" != "$branch" ] \
        || ! git merge-base --is-ancestor "$first" "origin/${BASE_BRANCH}"; then
        echo "bundle is not a merge of origin/${BASE_BRANCH} and ${UPSTREAM_REF}" >&2
        return 1
    fi

    count="$(git rev-list --count "origin/${BASE_BRANCH}..${upstream_head}")"
    git push -q -f origin "${tip}:refs/heads/${branch}"
    body="Merges ${count} commit(s) from \`${UPSTREAM_REPO}\` up to [\`${upstream_head:0:7}\`](https://github.com/${UPSTREAM_REPO}/commit/${upstream_head}).

The merge was clean and the unit and integration tests passed in the upstream-watch workflow, in a job without write access; generated tool lists were refreshed.

**Not merged automatically.** Review the upstream changes before merging: a merge into main is deployed by installs that follow main. Checks do not start on pull requests opened by the workflow token; close and reopen this pull request to run CI."
    pr="$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty')"
    if [ -z "$pr" ]; then
        gh label create upstream-sync --color 0E8A16 --description "New commits in the upstream repository" 2>/dev/null || true
        gh pr create --base "$BASE_BRANCH" --head "$branch" --label upstream-sync \
            --title "Merge upstream ${UPSTREAM_REPO}@${upstream_head:0:7}" --body "$body" >/dev/null
    else
        gh pr edit "$pr" --body "$body" >/dev/null
    fi
    out pr_opened
}

case "$MODE" in
    prepare) prepare ;;
    publish) publish ;;
    *) echo "usage: $0 [prepare|publish]" >&2; exit 2 ;;
esac
