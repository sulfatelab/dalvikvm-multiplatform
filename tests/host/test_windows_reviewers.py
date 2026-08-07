from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_ROOT = REPO_ROOT / "tests" / "support" / "windows"


def test_windows_reviewers_are_python_owned_and_syntax_valid():
    reviewers = sorted(REVIEWER_ROOT.glob("check_*.py"))
    assert len(reviewers) == 11
    assert not list(
        (REPO_ROOT / "tools" / "verify" / "windows_x64_phase1").glob("*.py")
    )
    for reviewer in reviewers:
        assert not reviewer.is_symlink()
        compile(reviewer.read_text(encoding="utf-8"), reviewer.as_posix(), "exec")


def test_win32_unicode_policy_ignores_literals_comments_and_jni_suffix_a_calls():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_win32_unicode_api_policy.py"),
        run_name="windows_unicode_api_reviewer",
    )
    findings = namespace["find_suffix_a_calls"](
        r'''
        // CreateFileA("comment");
        const char* diagnostic = "LoadLibraryA(module)";
        const char* raw = R"tag(CreateProcessA(NULL))tag";
        env->CallObjectMethodA(receiver, method, values);
        SSL_add_client_CA(ssl, certificate);
        NativeCrypto_EVP_PKEY_new_RSA(env, clazz, values);
        JNI_TRACE_PACKET_DATA(packet);
        HANDLE file = CreateFileA(path, 0, 0, NULL, 0, 0, NULL);
        ''',
        "probe.cc",
    )
    assert [finding["name"] for finding in findings] == [
        "CallObjectMethodA",
        "SSL_add_client_CA",
        "NativeCrypto_EVP_PKEY_new_RSA",
        "JNI_TRACE_PACKET_DATA",
        "CreateFileA",
    ]
    assert all(
        namespace["is_classified_non_win32_call"](name)
        for name in (
            "CallObjectMethodA",
            "SSL_add_client_CA",
            "NativeCrypto_EVP_PKEY_new_RSA",
            "JNI_TRACE_PACKET_DATA",
        )
    )


def test_win32_unicode_policy_classifies_current_cross_graph():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_win32_unicode_api_policy.py"),
        run_name="windows_unicode_api_reviewer",
    )
    compile_commands = (
        REPO_ROOT / "out/windows-x86_64-msvc/RelWithDebInfo/compile_commands.json"
    )
    if not compile_commands.is_file():
        return
    record = namespace["inspect_active_graph"](REPO_ROOT, compile_commands)
    assert record["ansi_call_count"] == 0
    assert record["ansi_source_count"] == 0
    assert record["ansi_api_count"] == 0
    assert record["unclassified_call_count"] == 0


def test_boundary_reviewer_resolves_private_pdb_publics():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_win32_boundary_unwind.py"),
        run_name="windows_boundary_unwind_reviewer",
    )
    section_output = """
  SECTION HEADER #1
     .text name
      2000 virtual size
      1000 virtual address
  SECTION HEADER #2
    .rdata name
      3000 virtual address
"""
    public_output = "\n".join(
        f"  1 | S_PUB32 [size = 1] `{name}`\n"
        f"      flags = none, addr = 0001:{offset}"
        for offset, name in enumerate(namespace["BOUNDARIES"], start=16)
    )
    sections = namespace["parse_section_virtual_addresses"](section_output)
    locations = namespace["parse_public_symbol_locations"](public_output)
    assert sections == {1: 0x1000, 2: 0x3000}
    assert {
        name: sections[section] + offset
        for name, (section, offset) in locations.items()
    } == {
        name: 0x1000 + offset
        for offset, name in enumerate(namespace["BOUNDARIES"], start=16)
    }


def test_cet_source_policy_rejects_raw_links_and_legacy_packagers():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_win32_cet_contract.py"),
        run_name="windows_cet_reviewer",
    )
    assert namespace["check_source_policy"](REPO_ROOT) == {
        "raw_links": 0,
        "legacy_packagers": 0,
    }


def test_w013_source_policy_matches_current_product_inventory():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_w013_source_policy.py"),
        run_name="windows_w013_source_reviewer",
    )
    counts = namespace["check_repository"](REPO_ROOT)
    assert counts == {
        "low_address_files": 8,
        "page_transition_files": 4,
        "mspace_lock_assertions": 2,
        "mspace_attachment_tokens": 6,
        "raw_mspace_creation_files": 1,
    }


def test_w013_mspace_policy_rejects_raw_creation_outside_wrapper(tmp_path):
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_w013_source_policy.py"),
        run_name="windows_w013_source_reviewer",
    )
    art = tmp_path / "vendor" / "art"
    allocator = art / "runtime" / "gc" / "allocator" / "art-dlmalloc.cc"
    space = art / "runtime" / "gc" / "space" / "dlmalloc_space.cc"
    bypass = art / "runtime" / "gc" / "space" / "bypass.cc"
    for path in (allocator, space, bypass):
        path.parent.mkdir(parents=True, exist_ok=True)
    allocator.write_text(
        "\n".join(namespace["MSPACE_ATTACHMENT_TOKENS"])
        + "\nvoid* p = create_mspace_with_base(base, size, false);\n",
        encoding="utf-8",
    )
    space.write_text("// direct owner dispatch only\n", encoding="utf-8")
    bypass.write_text("void* p = create_mspace(size, false);\n", encoding="utf-8")

    try:
        namespace["check_mspace_owner_policy"](tmp_path)
    except RuntimeError as error:
        assert "unexpected=['runtime/gc/space/bypass.cc']" in str(error)
    else:
        raise AssertionError("raw mspace creation outside the wrapper was accepted")
