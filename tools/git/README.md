# Git helpers for multiplatform remotes

## Remotes (local config)

| Repo | `origin` | `upstream` (nested) |
|------|----------|---------------------|
| main | `git@github.com:sulfatelab/dalvikvm-multiplatform.git` | — |
| nested | `git@github.com:sulfatelab/dalvikvm-multiplatform_<name>.git` | original AOSP googlesource URL |

Remotes are set on the agent workspace; they are not stored in commits (except
`.gitmodules` URLs for clone --recursive).

## Push to GitHub

```bash
# Plan pushes of current branches that are ahead of origin
tools/git/push_all_to_github.sh

# Push ahead current branches (SSH agent / keys required)
tools/git/push_all_to_github.sh --execute

# Plan/push every nested repo, then the main repo (the original behavior)
tools/git/push_all_to_github.sh --all
tools/git/push_all_to_github.sh --execute --all
```

Default mode visits every nested repo first, then the main repo. For each repo it
considers only the checked-out branch and skips the push when there are no commits
ahead of the matching `origin/<branch>` tracking ref. If that tracking ref does
not exist, the branch is treated as needing an initial push. Tags are not pushed
in default mode.

With `--all`, the order is **all nested** `artmp_android-16.0.0_r4` first, then
main `main`.

Tags (`--all` mode): only `android-16.0.0_r4` / `android-16.0.0_r*` /
`artmp_*` by default. Use `--all --all-tags` for full AOSP tag history (usually
not desired), or `--all --no-tags` for branches only.

## Unshallow all

After a shallow clone (or shallow vendor pins), convert nested trees to full history:

```bash
# plan
tools/git/unshallow_all.sh

# real unshallow (network required; prefers nested `upstream` AOSP remote)
tools/git/unshallow_all.sh --execute
```

Notes:

- Prefer unshallow **before** first GitHub push if you want complete history/tags on origin.
- Nested fetch remote preference: `upstream` (googlesource) then `origin`.
- Main is usually already complete; the script skips work when not shallow unless `--force-full-fetch`.
- Optional: `--nested-only`, `--main-only`, `--continue-on-error`.

## Status all

Show branch / HEAD / dirty / shallow for main + nested:

```bash
tools/git/status_all.sh              # short table
tools/git/status_all.sh --long       # full status for each
tools/git/status_all.sh --dirty-only  # only dirty / shallow / branch mismatch
tools/git/status_all.sh --porcelain   # TSV for scripts
```
