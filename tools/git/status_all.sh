#!/usr/bin/env bash
# Show git status for main + all nested vendor repos.
#
# Usage:
#   tools/git/status_all.sh
#   tools/git/status_all.sh --short          # one line per repo (default)
#   tools/git/status_all.sh --long           # full porcelain/status per dirty repo
#   tools/git/status_all.sh --porcelain      # machine-friendly short lines
#   tools/git/status_all.sh --dirty-only     # only dirty / mismatched repos
#   tools/git/status_all.sh --nested-only
#   tools/git/status_all.sh --main-only
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

MODE="short"          # short | long | porcelain
DIRTY_ONLY=0
NESTED=1
MAIN=1
BRANCH_EXPECT="artmp_android-16.0.0_r4"
MAIN_BRANCH_EXPECT="main"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --short) MODE=short; shift ;;
    --long) MODE=long; shift ;;
    --porcelain) MODE=porcelain; shift ;;
    --dirty-only) DIRTY_ONLY=1; shift ;;
    --nested-only) MAIN=0; NESTED=1; shift ;;
    --main-only) MAIN=1; NESTED=0; shift ;;
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

# Collect paths to report
PATHS=()
[[ "$MAIN" -eq 1 ]] && PATHS+=(".")
if [[ "$NESTED" -eq 1 ]]; then
  for p in "${NESTED_PATHS[@]}"; do
    PATHS+=("$p")
  done
fi

is_dirty() {
  local repo="$1"
  [[ -n "$(git -C "$repo" status --porcelain 2>/dev/null || true)" ]]
}

repo_line() {
  local rel="$1"
  local repo
  if [[ "$rel" == "." ]]; then
    repo="$REPO_ROOT"
  else
    repo="$REPO_ROOT/$rel"
  fi

  if [[ ! -d "$repo/.git" && ! -f "$repo/.git" ]]; then
    if [[ "$MODE" == "porcelain" ]]; then
      printf 'missing\t%s\n' "$rel"
    else
      printf '%-40s  MISSING_GIT\n' "$rel"
    fi
    return 1
  fi

  local branch sha short dirty_flag shallow remote_origin expected note
  branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  sha="$(git -C "$repo" rev-parse HEAD 2>/dev/null || echo '?')"
  short="${sha:0:12}"
  if is_dirty "$repo"; then
    dirty_flag="dirty"
  else
    dirty_flag="clean"
  fi
  if [[ "$(git -C "$repo" rev-parse --is-shallow-repository 2>/dev/null || echo false)" == "true" ]]; then
    shallow="shallow"
  else
    shallow="full"
  fi
  remote_origin="$(git -C "$repo" remote get-url origin 2>/dev/null || echo '-')"

  if [[ "$rel" == "." ]]; then
    expected="$MAIN_BRANCH_EXPECT"
  else
    expected="$BRANCH_EXPECT"
  fi
  note=""
  if [[ "$branch" != "$expected" && "$branch" != "HEAD" ]]; then
    note="branch!=$expected"
  fi
  if [[ "$branch" == "HEAD" ]]; then
    note="detached"
  fi

  # upstream tracking (best-effort)
  local ahead_behind=""
  if git -C "$repo" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    local counts
    counts="$(git -C "$repo" rev-list --left-right --count HEAD...@{u} 2>/dev/null || true)"
    if [[ -n "$counts" ]]; then
      local left right
      left="$(awk '{print $1}' <<<"$counts")"
      right="$(awk '{print $2}' <<<"$counts")"
      ahead_behind="ahead=$left behind=$right"
    fi
  fi

  local interesting=0
  [[ "$dirty_flag" == "dirty" ]] && interesting=1
  [[ -n "$note" ]] && interesting=1
  [[ "$shallow" == "shallow" ]] && interesting=1

  if [[ "$DIRTY_ONLY" -eq 1 && "$interesting" -eq 0 ]]; then
    return 0
  fi

  if [[ "$MODE" == "porcelain" ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$rel" "$branch" "$short" "$dirty_flag" "$shallow" "${note:-ok}" "$remote_origin"
    return 0
  fi

  if [[ "$MODE" == "short" ]]; then
    local flags="$dirty_flag,$shallow"
    [[ -n "$note" ]] && flags+=" ,$note"
    [[ -n "$ahead_behind" ]] && flags+=" ,$ahead_behind"
    printf '%-40s  %-28s  %s  [%s]\n' "$rel" "$branch" "$short" "$flags"
    return 0
  fi

  # long
  echo "======== $rel ========"
  echo "branch:  $branch  (expect $expected)"
  echo "HEAD:    $sha"
  echo "state:   $dirty_flag  history=$shallow  ${note:+($note)} ${ahead_behind}"
  echo "origin:  $remote_origin"
  if git -C "$repo" remote get-url upstream >/dev/null 2>&1; then
    echo "upstream:$(git -C "$repo" remote get-url upstream)"
  fi
  echo "--- status ---"
  git -C "$repo" status -sb
  if is_dirty "$repo"; then
    echo "--- porcelain ---"
    git -C "$repo" status --porcelain
  fi
  echo
}

total=0
dirty_n=0
shallow_n=0
missing_n=0

for rel in "${PATHS[@]}"; do
  total=$((total+1))
  repo="$REPO_ROOT/$rel"
  [[ "$rel" == "." ]] && repo="$REPO_ROOT"
  if [[ ! -d "$repo/.git" && ! -f "$repo/.git" ]]; then
    missing_n=$((missing_n+1))
  else
    is_dirty "$repo" && dirty_n=$((dirty_n+1))
    [[ "$(git -C "$repo" rev-parse --is-shallow-repository 2>/dev/null || echo false)" == "true" ]] && shallow_n=$((shallow_n+1))
  fi
  repo_line "$rel" || true
done

if [[ "$MODE" != "porcelain" ]]; then
  echo
  echo "summary: repos=$total dirty=$dirty_n shallow=$shallow_n missing=$missing_n"
fi

# Exit nonzero if any dirty when --dirty-only not forcing filter-only success?
# Always 0 unless missing repos.
[[ "$missing_n" -eq 0 ]]
