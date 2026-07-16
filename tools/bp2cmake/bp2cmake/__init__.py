"""bp2cmake — convert Android.bp (Soong/Blueprint) modules to CMakeLists.txt
for a GNU/Linux (glibc) host build of a minimal ART runtime.

The converter is structured in three layers (see project_scope.md section 5.5):

    Layer 1  parse + evaluate  -> normalized, config-resolved module graph
    Layer 2  port-policy overlay (human-owned) applied to the graph
    Layer 3  emit CMake

This package contains Layer 1 (parser, evaluator) and Layer 3 (emitter).
Layer 2 data lives outside the package, under //overlay.
"""

__version__ = "0.0.1"
