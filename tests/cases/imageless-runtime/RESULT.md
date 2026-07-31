# Imageless managed runtime result

## Contract

This case owns the Linux imageless managed-runtime smoke and GC-stress
contracts formerly run by `tools/verify/linux_hello`. It must eventually prove
that the shared multipath boot class path selects the Linux implementation,
that a D8-produced application runs with `-Ximage` unavailable and `-Xint`,
and that the non-moving heap survives the retained stress workload.

The former Bash runners are retired because they generated source and logs in
the checkout, searched stale `build/`, `dist/`, and `/tmp` locations, and
depended on undeclared ambient JDK and package state. Their removal is not a
claim that the managed behavior is covered by the native runtime gates.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | pending migration | historical only | 2026-07-29 18:07:49 UTC |
| `windows-x86_64-msvc` | yes | pending migration | pending migration | — |

## Historical Linux observation

The retained 2026-07-29 run reported `ART version 2.1.0 x86_64`, printed
`Hello from dalvikvm!`, and exited zero while interpreting a D8-produced Hello
class against the shared Linux/Windows boot JAR. That run depended on
machine-local build and temporary paths, so only the behavioral observation is
retained here; its paths and routine log were not durable evidence.

## Required replacement

The managed-asset migration must add the Java sources to this case, produce
all classes and JARs below `out/<target-id>/<build-type>/tests/`, invoke the
pinned `vendor/r8/r8.jar` through Python without a shell, declare the boot and
ICU inputs, and register separate Hello and GC-stress runtime gates. Until
those gates pass, this result remains historical rather than current
acceptance.
