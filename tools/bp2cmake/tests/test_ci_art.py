from tools import ci_art


def _actions(commands: list[list[str]]) -> list[str]:
    return [command[2] for command in commands if command[1] == str(ci_art.BUILD_FRONTEND)]


def test_linux_ci_cell_has_fresh_build_test_noop_and_stage(tmp_path):
    commands = ci_art.commands_for_cell(ci_art.CELLS["linux-product"], tmp_path)
    assert _actions(commands) == [
        "configure",
        "check-generated",
        "build",
        "build",
        "test",
        "stage",
    ]
    parallel_commands = [command for command in commands if "--parallel" in command]
    assert all(command[-1] == "32" for command in parallel_commands)


def test_windows_cross_ci_cell_does_not_claim_runtime_tests(tmp_path):
    commands = ci_art.commands_for_cell(ci_art.CELLS["windows-cross"], tmp_path)
    assert _actions(commands) == [
        "configure",
        "check-generated",
        "build",
        "build",
        "stage",
    ]
    assert all("--parallel" not in command or command[-1] == "32" for command in commands)


def test_native_windows_ci_cell_uses_vm_memory_limit(tmp_path):
    commands = ci_art.commands_for_cell(ci_art.CELLS["windows-native"], tmp_path)
    assert _actions(commands) == [
        "configure",
        "check-generated",
        "build",
        "build",
        "test",
        "stage",
    ]
    assert all("--parallel" not in command or command[-1] == "16" for command in commands)


def test_host_checks_are_python_only():
    commands = ci_art.commands_for_cell(ci_art.CELLS["host-checks"], None)
    assert commands[0] == [ci_art.sys.executable, str(ci_art.VCS_AUDIT)]
    assert commands[1][1:4] == ["-m", "pytest", "-q"]
    assert all(isinstance(command, list) for command in commands)


def test_run_key_is_a_portable_single_component(monkeypatch):
    monkeypatch.delenv(ci_art.CI_RUN_KEY_ENV, raising=False)
    assert ci_art._validated_run_key("1234-2") == "1234-2"
    for invalid in ("", "../escape", "bad/path", "space key"):
        try:
            ci_art._validated_run_key(invalid)
        except ci_art.CIError:
            pass
        else:
            raise AssertionError(f"accepted invalid run key {invalid!r}")
