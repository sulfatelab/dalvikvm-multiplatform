#!/usr/bin/env bash
# Unshallow main + all nested vendor repos (fix typo "unshadow").
#
# Useful after shallow clones / partial AOSP vendor pins so full history
# (and base tags) can be pushed or inspected.
#
# Preferred fetch remote for nested trees:
#   1) upstream  (AOSP googlesource — has full history)
#   2) origin    (GitHub sulfatelab — may be empty until first push)
#
# Usage:
#   tools/git/unshallow_all.sh                 # dry-run
#   tools/git/unshallow_all.sh --execute       # real unshallow/fetch
#   tools/git/unshallow_all.sh --execute --nested-only
#   tools/git/unshallow_all.sh --execute --main-only
#   tools/git/unshallow_all.sh --execute --force-full-fetch
#   tools/git/unshallow_all.sh --execute --continue-on-error
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

EXECUTE=0
NESTED=1
MAIN=1
FORCE_FULL=0
CONTINUE_ON_ERROR=0

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute|-x) EXECUTE=1; shift ;;
    --dry-run) EXECUTE=0; shift ;;
    --nested-only) MAIN=0; NESTED=1; shift ;;
    --main-only) MAIN=1; NESTED=0; shift ;;
    --force-full-fetch) FORCE_FULL=1; shift ;;
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

is_shallow() {
  local repo="$1"
  [[ "$(git -C "$repo" rev-parse --is-shallow-repository 2>/dev/null || echo false)" == "true" ]]
}

pick_fetch_remote() {
  # Prefer upstream (full AOSP) when present; else origin.
  local repo="$1"
  local remotes
  remotes="$(git -C "$repo" remote 2>/dev/null || true)"
  if grep -qx 'upstream' <<<"$remotes"; then
    echo upstream
    return 0
  fi
  if grep -qx 'origin' <<<"$remotes"; then
    echo origin
    return 0
  fi
  # first remote if any
  local first
  first="$(awk 'NF{print; exit}' <<<"$remotes")"
  if [[ -n "$first" ]]; then
    echo "$first"
    return 0
  fi
  return 1
}

unshallow_one() {
  local repo="$1"
  local label="$2"
  local remote shallow status=0

  if [[ ! -d "$repo/.git" && ! -f "$repo/.git" ]]; then
    echo "ERROR: not a git repo: $label" >&2
    return 1
  fi

  if ! remote="$(pick_fetch_remote "$repo")"; then
    echo "ERROR: $label has no remotes to fetch from" >&2
    return 1
  fi

  shallow=0
  if is_shallow "$repo"; then
    shallow=1
  fi

  local remote_url
  remote_url="$(git -C "$repo" remote get-url "$remote")"
  echo "==> $label  shallow=$shallow  fetch_remote=$remote ($remote_url)"

  if [[ "$shallow" -eq 1 ]]; then
    # Primary path: deepen into a complete history.
    if ! run git -C "$repo" fetch "$remote" --unshallow --tags; then
      echo "WARN: fetch --unshallow failed for $label; trying deepen + full fetch" >&2
      # Some remotes reject --unshallow; try progressive deepen then full.
      run git -C "$repo" fetch "$remote" --deepen=2147483647 --tags || status=1
      if is_shallow "$repo"; then
        # Last resort: re-fetch everything advertised.
        run git -C "$repo" fetch "$remote" --tags '+refs/heads/*:refs/remotes/'"$remote"'/*' || status=1
      fi
    fi
  else
    echo "    already complete history"
    if [[ "$FORCE_FULL" -eq 1 ]]; then
      run git -C "$repo" fetch "$remote" --tags || status=1
    fi
  fi

  # Report final state
  if [[ "$EXECUTE" -eq 1 ]]; then
    if is_shallow "$repo"; then
      echo "    RESULT: still shallow (may need network/remote with full history)"
      status=1
    else
      # show rough depth via rev-list count (can be large; limit noise)
      local commits
      commits="$(git -C "$repo" rev-list --count HEAD 2>/dev/null || echo '?')"
      echo "    RESULT: unshallow ok (reachable commits from HEAD: $commits)"
    fi
  else
    if [[ "$shallow" -eq 1 ]]; then
      echo "    plan: git fetch $remote --unshallow --tags"
    fi
  fi
  return "$status"
}

failures=0
ok=0
skipped=0

if [[ "$NESTED" -eq 1 ]]; then
  echo "### Nested repos (${#NESTED_PATHS[@]})"
  for path in "${NESTED_PATHS[@]}"; do
    if unshallow_one "$REPO_ROOT/$path" "$path"; then
      ok=$((ok+1))
    else
      failures=$((failures+1))
      [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
    fi
  done
fi

if [[ "$MAIN" -eq 1 ]]; then
  echo "### Main repo"
  if unshallow_one "$REPO_ROOT" "."; then
    ok=$((ok+1))
  else
    failures=$((failures+1))
    [[ "$CONTINUE_ON_ERROR" -eq 1 ]] || exit 1
  fi
fi

echo
if [[ "$EXECUTE" -eq 1 ]]; then
  echo "Done. ok=$ok failures=$failures"
else
  echo "Dry-run only. Re-run with --execute to unshallow (network + remotes required)."
  echo "Planned ok_parse=$ok failures=$failures"
  echo "Note: nested art/libcore/icu are often shallow; fetch prefers 'upstream' (AOSP)."
fi
[[ "$failures" -eq 0 ]]
