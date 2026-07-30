#!/usr/bin/env bash
# Push each nested repo's current branch when it is ahead, then the main repo's.
# Use --all for the original fixed-branch and selected-tag behavior.
#
# In --all mode, the default tag policy is ONLY explicit product tags matching:
#   android-16.0.0_r4, android-16.0.0_r*, artmp_*
# Nested AOSP trees often have 1000+ tags; those are NOT pushed by default.
# Use --all-tags only if you intentionally want full AOSP tag history on GitHub.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BRANCH_DEFAULT="artmp_android-16.0.0_r4"
MAIN_BRANCH="main"
REMOTE="origin"
# Explicit product tag globs only (no --points-at flood from AOSP history).
PRODUCT_TAG_GLOBS=(
  "android-16.0.0_r4"
  "android-16.0.0_r*"
  "artmp_*"
)

EXECUTE=0
ALL_REPOS=0
TAG_MODE="product"   # product | all | none
NESTED=1
MAIN=1
FORCE_LEASE=0
CONTINUE_ON_ERROR=0
TAG_OPTION=0
LAST_PUSH_SKIPPED=0

usage() {
  cat <<'EOF'
Push current branches when ahead, or use --all for the original broad behavior.

Usage:
  tools/git/push_all_to_github.sh [--execute]
  tools/git/push_all_to_github.sh --all [--execute] [options]

Default mode:
  --execute, -x           Push each nested repo's current branch when ahead of
                          origin/<branch>, then do the same for the main repo.
                          Without this flag, show the plan.
  --dry-run               Show the plan without pushing (the default).
  --force-with-lease      Add --force-with-lease to branch pushes.
  --nested-only           Exclude the main repo.
  --main-only             Exclude nested repos.
  --continue-on-error     Continue after a failed repository or tag push.

Full repository mode:
  --all                   Preserve the original behavior: push all nested repos,
                          then the main repo, including product tags.
  --all-tags              Push every local tag (requires --all).
  --no-tags               Do not push tags (requires --all).
  --product-tags          Push product tags only (requires --all; the default).

Other:
  -h, --help              Show this help.
EOF
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|-x) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    --all) ALL_REPOS=1; shift ;;
    --all-tags) TAG_MODE=all; TAG_OPTION=1; shift ;;
    --no-tags) TAG_MODE=none; TAG_OPTION=1; shift ;;
    --product-tags) TAG_MODE=product; TAG_OPTION=1; shift ;;
    --nested-only) MAIN=0; NESTED=1; shift ;;
    --main-only) MAIN=1; NESTED=0; shift ;;
    --force-with-lease) FORCE_LEASE=1; shift ;;
    --continue-on-error) CONTINUE_ON_ERROR=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

if [[ "$ALL_REPOS" -eq 0 && "$TAG_OPTION" -eq 1 ]]; then
  echo "error: tag options require --all" >&2
  exit 1
fi

NESTED_PATHS=()
if [[ "$NESTED" -eq 1 ]]; then
  if [[ ! -f "$REPO_ROOT/.gitmodules" ]]; then
    echo "error: .gitmodules not found in $REPO_ROOT" >&2
    exit 1
  fi

  mapfile -t NESTED_PATHS < <(
    git config -f "$REPO_ROOT/.gitmodules" --get-regexp '^submodule\..*\.path$' \
      | awk '{print $2}' | sort
  )
fi

run() {
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "+ $*"
    "$@"
  else
    echo "[dry-run] $*"
  fi
}

collect_product_tags() {
  local repo="$1"
  local -a tags=()
  local t
  while IFS= read -r t; do
    [[ -n "$t" ]] && tags+=("$t")
  done < <(git -C "$repo" tag --list "${PRODUCT_TAG_GLOBS[@]}" 2>/dev/null | sort -u)
  if [[ ${#tags[@]} -gt 0 ]]; then
    printf '%s\n' "${tags[@]}"
  fi
}

push_repo_branch() {
  local repo="$1"
  local branch="$2"
  local label="$3"
  local only_if_ahead="${4:-0}"
  local url
  LAST_PUSH_SKIPPED=0
  url="$(git -C "$repo" remote get-url "$REMOTE" 2>/dev/null || true)"
  if [[ -z "$url" ]]; then
    echo "ERROR: $label has no remote '$REMOTE'" >&2
    return 1
  fi
  if ! git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
    echo "ERROR: $label missing branch $branch" >&2
    return 1
  fi

  echo "==> $label  branch=$branch  remote=$url"

  if [[ "$only_if_ahead" -eq 1 ]]; then
    local remote_ref="refs/remotes/$REMOTE/$branch"
    if git -C "$repo" show-ref --verify --quiet "$remote_ref"; then
      local ahead
      ahead="$(git -C "$repo" rev-list --count "$remote_ref..refs/heads/$branch")"
      echo "    ahead of $REMOTE/$branch: $ahead"
      if [[ "$ahead" -eq 0 ]]; then
        echo "    skip: current branch has no commits to push"
        LAST_PUSH_SKIPPED=1
        return 0
      fi
    else
      echo "    ahead of $REMOTE/$branch: initial push (no remote-tracking ref)"
    fi
  fi

  local -a args=( -C "$repo" push -u "$REMOTE" "$branch" )
  if [[ "$FORCE_LEASE" -eq 1 ]]; then
    args+=( --force-with-lease )
  fi
  if ! run git "${args[@]}"; then
    echo "ERROR: branch push failed for $label" >&2
    return 1
  fi
  return 0
}

push_repo_tags() {
  local repo="$1"
  local label="$2"

  [[ "$TAG_MODE" == "none" ]] && return 0

  if [[ "$TAG_MODE" == "all" ]]; then
    local n
    n="$(git -C "$repo" tag | wc -l | tr -d ' ')"
    echo "    tags: pushing ALL local tags ($n)"
    if [[ "$n" -gt 200 ]]; then
      echo "    WARNING: large tag set ($n). Prefer default product tags unless intentional." >&2
    fi
    if ! run git -C "$repo" push "$REMOTE" --tags; then
      echo "ERROR: --tags push failed for $label" >&2
      return 1
    fi
    return 0
  fi

  mapfile -t tags < <(collect_product_tags "$repo")
  if [[ ${#tags[@]} -eq 0 ]]; then
    echo "    tags: none (product policy)"
    return 0
  fi
  echo "    tags: ${tags[*]}"
  local t failed=0
  for t in "${tags[@]}"; do
    if ! run git -C "$repo" push "$REMOTE" "refs/tags/$t"; then
      echo "ERROR: tag push failed: $label tag=$t" >&2
      failed=1
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || return 1
    fi
  done
  return "$failed"
}

failures=0
ok=0
skipped=0

push_current_repo_branch() {
  local repo="$1"
  local label="$2"
  local branch
  branch="$(git -C "$repo" symbolic-ref --quiet --short HEAD || true)"
  if [[ -z "$branch" ]]; then
    echo "ERROR: $label has a detached HEAD; check out a branch or use --all" >&2
    return 1
  fi

  if ! push_repo_branch "$repo" "$branch" "$label" 1; then
    return 1
  fi
  if [[ "$LAST_PUSH_SKIPPED" -eq 1 ]]; then
    skipped=$((skipped+1))
  else
    ok=$((ok+1))
  fi
}

if [[ "$ALL_REPOS" -eq 0 ]]; then
  if [[ "$NESTED" -eq 1 ]]; then
    echo "### Nested repos (${#NESTED_PATHS[@]}) — current branches, nested first"
    for path in "${NESTED_PATHS[@]}"; do
      repo="$REPO_ROOT/$path"
      if [[ ! -d "$repo/.git" && ! -f "$repo/.git" ]]; then
        echo "ERROR: missing nested git at $path" >&2
        failures=$((failures+1))
        [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
        continue
      fi
      if ! push_current_repo_branch "$repo" "$path"; then
        failures=$((failures+1))
        [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
      fi
    done
  fi

  if [[ "$MAIN" -eq 1 ]]; then
    echo "### Main repo — current branch, after nested"
    if ! push_current_repo_branch "$REPO_ROOT" "."; then
      failures=$((failures+1))
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
    fi
  fi

  echo
  if [[ "$EXECUTE" -eq 1 ]]; then
    echo "Done. pushed_units=$ok skipped_units=$skipped failures=$failures mode=current-branches"
  else
    echo "Dry-run only. Re-run with --execute to push ahead current branches (SSH agent required)."
    echo "Planned units=$ok skipped_units=$skipped failures=$failures mode=current-branches"
  fi
  [[ "$failures" -eq 0 ]]
  exit
fi

if [[ "$NESTED" -eq 1 ]]; then
  echo "### Nested repos (${#NESTED_PATHS[@]}) — push order: nested first"
  for path in "${NESTED_PATHS[@]}"; do
    repo="$REPO_ROOT/$path"
    if [[ ! -d "$repo/.git" && ! -f "$repo/.git" ]]; then
      echo "ERROR: missing nested git at $path" >&2
      failures=$((failures+1))
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
      continue
    fi
    branch="$BRANCH_DEFAULT"
    if ! git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
      branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD)"
      echo "WARN: $path has no $BRANCH_DEFAULT; using $branch" >&2
    fi
    if push_repo_branch "$repo" "$branch" "$path"; then
      if push_repo_tags "$repo" "$path"; then
        ok=$((ok+1))
      else
        failures=$((failures+1))
        [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
      fi
    else
      failures=$((failures+1))
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
    fi
  done
fi

if [[ "$MAIN" -eq 1 ]]; then
  echo "### Main repo — after nested"
  if push_repo_branch "$REPO_ROOT" "$MAIN_BRANCH" "."; then
    if push_repo_tags "$REPO_ROOT" "."; then
      ok=$((ok+1))
    else
      failures=$((failures+1))
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
    fi
  else
    failures=$((failures+1))
    [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
  fi
fi

echo
if [[ "$EXECUTE" -eq 1 ]]; then
  echo "Done. ok_units=$ok failures=$failures tag_mode=$TAG_MODE"
else
  echo "Dry-run only. Re-run with --execute to push (SSH agent required)."
  echo "Planned units ok_parse=$ok failures=$failures tag_mode=$TAG_MODE"
fi
[[ "$failures" -eq 0 ]]
