# libexpat (vendored)

Source: [libexpat 2.6.4](https://github.com/libexpat/libexpat/releases/tag/R_2_6_4)
License: MIT (`COPYING`)

Used by AOSP `org.apache.harmony.xml.ExpatParser` (`libjavacore`) on Win64 PE.
Only `lib/` sources are kept; built as a static library in
`tools/verify/win64_libcore_icu` and linked into `libjavacore.dll`.
