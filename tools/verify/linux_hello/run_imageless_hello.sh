#!/usr/bin/env bash
# L-005: Linux multiplatform imageless Hello / boot.jar CI gate
#
# Runs Hello.main against the converter-built host dalvikvm using imageless
# boot.jar interpretation (-Ximage:/nonexistent-no-boot-image, -Xint).
#
# Linux and Win64 use the same shared multipath boot.jar bytes. The ELF runtime
# must select UnixFileSystem from a jar that also carries WinNTFileSystem and
# the VMRuntime runtime-OS selector.
#
# Usage:
#   tools/verify/linux_hello/run_imageless_hello.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
NATIVE="${MDVM_NATIVE:-$ROOT/build/native}"
TIMEOUT_SEC="${MDVM_TIMEOUT:-180}"
OUT_DIR="$ROOT/tools/verify/linux_hello"
RUN_DIR="${MDVM_RUN_DIR:-/tmp/mdvm_linux_hello_run}"
LOG="$OUT_DIR/last_run.log"

DALVIKVM="$NATIVE/dalvikvm"
if [[ ! -x "$DALVIKVM" ]]; then
  echo "ERROR: missing $DALVIKVM (build Linux native target first)" >&2
  exit 2
fi

pick_first() {
  local f
  for f in "$@"; do
    if [[ -f "$f" ]]; then
      echo "$f"
      return 0
    fi
  done
  return 1
}

is_shared_boot_jar() {
  local jar="$1"
  python3 - "$jar" <<'PY2'
import zipfile,sys
path=sys.argv[1]
z=zipfile.ZipFile(path)
data=b"".join(z.read(n) for n in z.namelist() if n.endswith(".dex"))
has_unix = b"UnixFileSystem" in data
has_winnt = b"WinNTFileSystem" in data
has_osdet = b"isWindowsOs" in data
has_osprop = b"dalvik.vm.multiplatform.internal.os" in data
if has_unix and has_winnt and has_osdet and has_osprop:
    sys.exit(0)
sys.exit(1)
PY2
}

BOOT_JAR="${MDVM_BOOT_JAR:-}"
if [[ -n "$BOOT_JAR" ]]; then
  if ! is_shared_boot_jar "$BOOT_JAR"; then
    echo "ERROR: MDVM_BOOT_JAR is not the shared multipath product boot.jar: $BOOT_JAR" >&2
    exit 2
  fi
else
  BOOT_JAR=""
  for cand in \
      "$ROOT/build/win64_phase1/run/boot.jar" \
      /tmp/vm/run/boot.jar \
      "$OUT_DIR/boot.jar" \
      "$ROOT/dist/linux_hello/boot.jar"; do
    if [[ -f "$cand" ]] && is_shared_boot_jar "$cand"; then
      BOOT_JAR="$cand"
      break
    fi
  done
fi
if [[ -z "${BOOT_JAR:-}" ]]; then
  echo "ERROR: no shared multipath product boot.jar found." >&2
  echo "  Build/stage the single Linux+Win64 jar with tools/bootjar/build_win64.sh." >&2
  exit 2
fi

HELLO_JAR="${MDVM_HELLO:-}"
if [[ -z "$HELLO_JAR" ]]; then
  HELLO_JAR="$(pick_first \
    "$ROOT/build/win64_phase1/run/hello.jar" \
    /tmp/vm/run/hello.jar || true)"
fi

mkdir -p "$RUN_DIR/data" "$RUN_DIR/icu" "$OUT_DIR"
cp -f "$BOOT_JAR" "$RUN_DIR/boot.jar"

if [[ -n "${HELLO_JAR:-}" && -f "$HELLO_JAR" ]]; then
  cp -f "$HELLO_JAR" "$RUN_DIR/hello.jar"
else
  echo "building minimal Hello.jar..."
  mkdir -p "$OUT_DIR/src" "$OUT_DIR/classes"
  cat > "$OUT_DIR/src/Hello.java" <<'JAVA'
public class Hello {
  public static void main(String[] args) {
    System.out.println("Hello from dalvikvm!");
  }
}
JAVA
  JAVAC="${MDVM_JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
  R8JAR="${MDVM_R8JAR:-$ROOT/vendor/r8/r8.jar}"
  "$JAVAC" -d "$OUT_DIR/classes" --release 8 "$OUT_DIR/src/Hello.java"
  java -cp "$R8JAR" com.android.tools.r8.D8 --release --min-api 31 \
    --output "$RUN_DIR/hello.jar" "$OUT_DIR/classes/Hello.class"
fi

if [[ ! -f "$RUN_DIR/icu/icudt72l.dat" ]]; then
  for cand in \
      "$ROOT/build/win64_phase1/run/icu/icudt72l.dat" \
      "$ROOT/vendor/icu/icu4c/source/stubdata/icudt72l.dat" \
      /tmp/vm/run/icu/icudt72l.dat; do
    if [[ -f "$cand" ]]; then
      cp -f "$cand" "$RUN_DIR/icu/icudt72l.dat"
      break
    fi
  done
fi

export ANDROID_ROOT="$RUN_DIR"
export ANDROID_ART_ROOT="$RUN_DIR"
export ANDROID_I18N_ROOT="$RUN_DIR"
export ANDROID_DATA="$RUN_DIR/data"
export ICU_DATA="$RUN_DIR/icu"
export LD_LIBRARY_PATH="$NATIVE${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

{
  echo "=== L-005 Linux imageless Hello gate ==="
  echo "date: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "dalvikvm: $DALVIKVM"
  echo "boot.jar: $BOOT_JAR -> $RUN_DIR/boot.jar ($(wc -c < "$RUN_DIR/boot.jar") bytes)"
  echo "hello.jar: $RUN_DIR/hello.jar ($(wc -c < "$RUN_DIR/hello.jar") bytes)"
  echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
  echo
  echo "--- showversion ---"
  "$DALVIKVM" -showversion || true
  echo
  echo "--- Hello ---"
  set +e
  # Linux ART requires sigchain for a started runtime; do NOT pass -Xno-sig-chain.
  timeout "$TIMEOUT_SEC" "$DALVIKVM" \
    -Xbootclasspath:"$RUN_DIR/boot.jar" \
    -Xbootclasspath-locations:"$RUN_DIR/boot.jar" \
    -Ximage:/nonexistent-no-boot-image \
    -XjdwpProvider:none \
    -Xint \
    -Xms64m -Xmx512m \
    -cp "$RUN_DIR/hello.jar" Hello
  rc=$?
  set -e
  echo
  echo "exit=$rc"
} | tee "$LOG"

if grep -q 'Hello from dalvikvm!' "$LOG" && grep -q '^exit=0$' "$LOG"; then
  echo "L-005 PASS" | tee -a "$LOG"
  {
    echo "# L-005 Linux imageless Hello gate"
    echo
    echo "**Status:** PASS"
    echo "**Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "**Host:** $(hostname)"
    echo
    echo "## Command"
    echo
    echo '```'
    echo "tools/verify/linux_hello/run_imageless_hello.sh"
    echo '```'
    echo
    echo "## Observed"
    echo
    echo "- \`dalvikvm -showversion\` prints ART version"
    echo "- Imageless \`-Xint\` Hello.main prints \`Hello from dalvikvm!\` and exits 0"
    echo "- boot.jar is the shared Linux+Win64 multipath artifact; ELF selected UnixFileSystem"
    echo
    echo "## Artifacts"
    echo
    echo "- log: \`tools/verify/linux_hello/last_run.log\`"
    echo "- staged run dir: \`$RUN_DIR\`"
    echo "- dalvikvm: \`$DALVIKVM\`"
    echo "- boot.jar source: \`$BOOT_JAR\`"
  } > "$OUT_DIR/RESULT.md"
  exit 0
fi

echo "L-005 FAIL (see $LOG)" >&2
exit 1
