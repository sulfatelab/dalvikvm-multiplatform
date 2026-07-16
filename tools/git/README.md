# Git helpers for multiplatform remotes

## Remotes (local config)

| Repo | `origin` | `upstream` (nested) |
|------|----------|---------------------|
| main | `git@github.com:sulfatelab/dalvikvm-multiplatform.git` | — |
| nested | `git@github.com:sulfatelab/dalvikvm-multiplatform_<name>.git` | original AOSP googlesource URL |

Remotes are set on the agent workspace; they are not stored in commits (except
`.gitmodules` URLs for clone --recursive).

## Push all

```bash
# plan
tools/git/push_all_to_github.sh

# real push (SSH agent / keys required)
tools/git/push_all_to_github.sh --execute
```

Order: **all nested** `artmp_android-16.0.0_r4` first, then main `main`.

Tags (default): only `android-16.0.0_r4` / `android-16.0.0_r*` / `artmp_*`.  
Use `--all-tags` for full AOSP tag history (usually not desired).  
Use `--no-tags` for branches only.

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

