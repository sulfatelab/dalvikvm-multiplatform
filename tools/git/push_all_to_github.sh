#!/usr/bin/env bash
# Push all nested artmp repos (and selected tags), then the main multiplatform repo.
#
# Default tag policy: ONLY explicit product tags matching:
#   android-16.0.0_r4, android-16.0.0_r*, artmp_*
# Nested AOSP trees often have 1000+ tags; those are NOT pushed by default.
# Use --all-tags only if you intentionally want full AOSP tag history on GitHub.
#
# Usage:
#   tools/git/push_all_to_github.sh              # dry-run plan
#   tools/git/push_all_to_github.sh --execute    # real push (needs SSH agent)
#   tools/git/push_all_to_github.sh --execute --all-tags
#   tools/git/push_all_to_github.sh --execute --no-tags
#   tools/git/push_all_to_github.sh --execute --nested-only
#   tools/git/push_all_to_github.sh --execute --main-only
#   tools/git/push_all_to_github.sh --execute --force-with-lease
#   tools/git/push_all_to_github.sh --execute --continue-on-error
#
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
TAG_MODE="product"   # product | all | none
NESTED=1
MAIN=1
FORCE_LEASE=0
CONTINUE_ON_ERROR=0

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|-x) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    --all-tags) TAG_MODE=all; shift ;;
    --no-tags) TAG_MODE=none; shift ;;
    --product-tags) TAG_MODE=product; shift ;;
    --nested-only) MAIN=0; NESTED=1; shift ;;
    --main-only) MAIN=1; NESTED=0; shift ;;
    --force-with-lease) FORCE_LEASE=1; shift ;;
    --continue-on-error) CONTINUE_ON_ERROR=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

if [[ ! -f "$REPO_ROOT/.gitmodules" ]]; then
  echo "error: .gitmodules not found in $REPO_ROOT" >&2
  exit 1
fi

mapfile -t NESTED_PATHS < <(
  git config -f "$REPO_ROOT/.gitmodules" --get-regexp '^submodule\..*\.path$' \
    | awk '{print $2}' | sort
)

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
  local url
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
