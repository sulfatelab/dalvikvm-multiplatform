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
