# Historical W-025 package evidence

W-025 is maintained by `art-test-stage-w025` in the unified CMake/Ninja test
catalog. The package producers and their Bash, PowerShell, and Wine execution
wrappers were retired after the unified stage passed twice on Windows Server
2025 and its structural review passed in the Linux-hosted Windows cross tree.

The files retained here are historical accepted results, checklists, package
checkers/reviewers, and compact text evidence for the four original JIT
milestones. They can review an already archived package of the matching old
format; they are not active build or test entry points and may refer to runner
files that no longer exist. Current reproduction is:

```text
python tools/build_art.py build --target-id windows-x86_64-msvc --build-type RelWithDebInfo --cmake-target art-test-stage-w025 --parallel 16
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w025
```

Use `--parallel 32` on the 32 GiB Linux host and `--parallel 16` on the 16 GiB
Windows VM. No archived executable, DLL, JAR, ZIP, or dump belongs in VCS.
