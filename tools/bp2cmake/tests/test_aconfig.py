"""Tests for the aconfig C++ header generator (android-16+ feature flags)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bp2cmake.aconfig import parse_aconfig, render_header

_RO = '''
package: "com.android.art.flags"
container: "com.android.art"
# a comment with package: "should.be.ignored"
flag {
  name: "virtual_thread_impl_v1"
  namespace: "core_libraries"
  description: "x"
  bug: "1"
  is_fixed_read_only: true
  is_exported: false
}
flag {
  name: "weak_const_string"
  is_fixed_read_only: true
}
'''

_RW = '''
package: "com.android.art.rw.flags"
flag {
  name: "test_rw_flag"
  is_fixed_read_only: false
}
'''


def test_parse_package_and_flags():
    pkg = parse_aconfig(_RO)
    assert pkg.package == "com.android.art.flags"
    assert pkg.namespace == "com::android::art::flags"
    assert pkg.c_prefix == "com_android_art_flags"
    names = [f.name for f in pkg.flags]
    assert names == ["virtual_thread_impl_v1", "weak_const_string"]
    assert all(f.read_only for f in pkg.flags)
    assert all(not f.enabled for f in pkg.flags)  # no state: ENABLED -> default off


def test_render_readonly_constexpr_and_macro():
    h = render_header(parse_aconfig(_RO))
    # constexpr accessor (used in static_assert/constexpr contexts).
    assert "inline constexpr bool virtual_thread_impl_v1() { return false; }" in h
    # uppercase compile-time macro that thread.h compares against.
    assert "#define COM_ANDROID_ART_FLAGS_VIRTUAL_THREAD_IMPL_V1 false" in h
    # namespaced + C-style accessor both present.
    assert "namespace com { namespace android { namespace art { namespace flags {" in h
    assert "bool com_android_art_flags_weak_const_string() { return false; }" in h


def test_render_readwrite_not_constexpr():
    h = render_header(parse_aconfig(_RW))
    assert "inline bool test_rw_flag() { return false; }" in h
    assert "constexpr bool test_rw_flag" not in h
    # rw flags get no compile-time macro.
    assert "#define COM_ANDROID_ART_RW_FLAGS_TEST_RW_FLAG" not in h
    assert "bool com_android_art_rw_flags_test_rw_flag() { return false; }" in h
