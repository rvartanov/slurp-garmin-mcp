#!/usr/bin/env bash
# Report upstream commits (Taxuspt/garmin_mcp) that this fork has not merged yet.
#
# Keeps one open GitHub issue, labelled upstream-sync, with the list of
# unmerged commits and the files both sides changed (likely merge conflicts).
# It comments on the issue only when upstream has moved since the last run,
# and closes it once everything is merged.
#
#   git fetch upstream main && scripts/check_upstream.sh            # needs gh + GH_TOKEN
#   DRY_RUN=1 scripts/check_upstream.sh                             # print, change nothing
#
# Environment: UPSTREAM_REF (default upstream/main), BASE_REF (default HEAD),
# UPSTREAM_REPO (default Taxuspt/garmin_mcp), LABEL (default upstream-sync).
set -euo pipefail

UPSTREAM_REF="${UPSTREAM_REF:-upstream/main}"
BASE_REF="${BASE_REF:-HEAD}"
UPSTREAM_REPO="${UPSTREAM_REPO:-Taxuspt/garmin_mcp}"
LABEL="${LABEL:-upstream-sync}"
DRY_RUN="${DRY_RUN:-}"

upstream_head="$(git rev-parse --verify "${UPSTREAM_REF}^{commit}")"
base_head="$(git rev-parse --verify "${BASE_REF}^{commit}")"
count="$(git rev-list --count "${base_head}..${upstream_head}")"
marker="<!-- upstream-head: ${upstream_head} -->"

existing=""
if [ -z "$DRY_RUN" ]; then
    existing="$(gh issue list --state open --label "$LABEL" --limit 1 --json number --jq '.[0].number // empty')"
fi

if [ "$count" -eq 0 ]; then
    echo "Up to date with ${UPSTREAM_REPO} (${upstream_head:0:7})."
    if [ -n "$existing" ]; then
        gh issue close "$existing" --comment "All upstream commits up to \`${upstream_head:0:7}\` are merged."
    fi
    exit 0
fi

merge_base="$(git merge-base "$base_head" "$upstream_head")"
body="$(mktemp)"
trap 'rm -f "$body"' EXIT
{
    echo "$marker"
    echo "**${count}** commit(s) on \`${UPSTREAM_REPO}\` main are not merged into this fork yet."
    echo
    echo "Upstream head: [\`${upstream_head:0:7}\`](https://github.com/${UPSTREAM_REPO}/commit/${upstream_head}) · merge base: \`${merge_base:0:7}\` · [compare](https://github.com/${UPSTREAM_REPO}/compare/${merge_base}...${upstream_head})"
    echo
    echo "### Commits"
    echo
    git log --reverse --no-merges --format="- [\`%h\`](https://github.com/${UPSTREAM_REPO}/commit/%H) %s (%an, %as)" \
        "${base_head}..${upstream_head}"
    echo
    echo "### Files changed on both sides"
    echo
    overlap="$(comm -12 \
        <(git diff --name-only "$merge_base" "$upstream_head" | sort) \
        <(git diff --name-only "$merge_base" "$base_head" | sort))"
    if [ -n "$overlap" ]; then
        echo "Expect merge conflicts here:"
        echo
        while IFS= read -r file; do echo "- \`${file}\`"; done <<<"$overlap"
    else
        echo "None: the merge should apply cleanly."
    fi
    echo
    echo "### Merging"
    echo
    echo '```bash'
    echo "git fetch upstream && git switch -c merge-upstream-${upstream_head:0:7} main"
    echo "git merge upstream/main"
    echo "uv run pytest -q && uv run python scripts/generate_tools_doc.py && uv run python scripts/generate_dxt_tools.py"
    echo '```'
    echo
    echo "Then open a pull request, or review the \`upstream-sync\` pull request the upstream watch opened when the merge was clean and green. Nothing is merged automatically; this issue closes itself after the merge."
} >"$body"

title="Upstream: ${count} unmerged commit(s) from ${UPSTREAM_REPO}"

if [ -n "$DRY_RUN" ]; then
    echo "# ${title}"
    cat "$body"
    exit 0
fi

if [ -z "$existing" ]; then
    gh label create "$LABEL" --color 0E8A16 --description "New commits in the upstream repository" 2>/dev/null || true
    gh issue create --title "$title" --label "$LABEL" --body-file "$body"
    exit 0
fi

if gh issue view "$existing" --json body --jq .body | grep -qF "$marker"; then
    echo "Issue #${existing} already lists upstream ${upstream_head:0:7}."
    exit 0
fi
gh issue edit "$existing" --title "$title" --body-file "$body"
gh issue comment "$existing" --body "Upstream moved to \`${upstream_head:0:7}\`: ${count} unmerged commit(s). The list above is updated."
