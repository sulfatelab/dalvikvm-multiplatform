from pathlib import Path

import pytest

from bp2cmake.local_config import CI_CONFIG_ENV, LocalConfigError, load_local_config


@pytest.fixture(autouse=True)
def _clear_ci_config(monkeypatch):
    monkeypatch.delenv(CI_CONFIG_ENV, raising=False)


def _literal(path: Path) -> str:
    return "'" + str(path) + "'"


def test_absent_local_config_is_empty(tmp_path):
    config = load_local_config(tmp_path)
    assert config.source_file is None
    assert config.tools == {}
    assert config.targets == {}
    assert config.target_runners == {}


def test_loads_valid_path_bindings(tmp_path):
    llvm = tmp_path / "llvm"
    jdk = tmp_path / "jdk"
    bundle = tmp_path / "windows-bundle"
    llvm.mkdir()
    jdk.mkdir()
    bundle.mkdir()
    output = tmp_path / "out-does-not-exist"
    (tmp_path / ".art-build.local.toml").write_text(
        "[tools]\n"
        f"llvm_root = {_literal(llvm)}\n"
        f"jdk_root = {_literal(jdk)}\n"
        "[build]\n"
        f"output_root = {_literal(output)}\n"
        '[targets."windows-x86_64-msvc"]\n'
        f"bundle_root = {_literal(bundle)}\n",
        encoding="utf-8",
    )

    config = load_local_config(tmp_path)
    assert config.tools["llvm_root"] == llvm
    assert config.tools["jdk_root"] == jdk
    assert config.output_root == output
    assert config.target_bindings("windows-x86_64-msvc")["bundle_root"] == bundle


def test_rejects_policy_in_local_config(tmp_path):
    (tmp_path / ".art-build.local.toml").write_text(
        '[targets."windows-x86_64-msvc"]\ncompiler_flags = "-O3"\n',
        encoding="utf-8",
    )
    with pytest.raises(LocalConfigError, match="unsupported keys"):
        load_local_config(tmp_path)


def test_rejects_noncanonical_target_key(tmp_path):
    (tmp_path / ".art-build.local.toml").write_text(
        '[targets."windows-x64"]\n', encoding="utf-8"
    )
    with pytest.raises(LocalConfigError, match="windows-x86_64-msvc"):
        load_local_config(tmp_path)


def test_loads_exact_target_runner(tmp_path):
    runner = tmp_path / "qemu-aarch64"
    runner.write_bytes(b"runner")
    (tmp_path / ".art-build.local.toml").write_text(
        '[target_runners]\n"linux-aarch64-gnu" = '
        f"{_literal(runner)}\n",
        encoding="utf-8",
    )

    config = load_local_config(tmp_path)

    assert config.target_runners == {"linux-aarch64-gnu": runner}


def test_rejects_noncanonical_target_runner_key(tmp_path):
    runner = tmp_path / "qemu-aarch64"
    runner.write_bytes(b"runner")
    (tmp_path / ".art-build.local.toml").write_text(
        '[target_runners]\n"linux-arm64" = '
        f"{_literal(runner)}\n",
        encoding="utf-8",
    )

    with pytest.raises(LocalConfigError, match="linux-aarch64-gnu"):
        load_local_config(tmp_path)


def test_rejects_relative_path(tmp_path):
    (tmp_path / ".art-build.local.toml").write_text(
        '[tools]\nllvm_root = "relative/llvm"\n', encoding="utf-8"
    )
    with pytest.raises(LocalConfigError, match="must be absolute"):
        load_local_config(tmp_path)


def test_rejects_symlink_component(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create a directory symlink")
    (tmp_path / ".art-build.local.toml").write_text(
        "[tools]\n" f"llvm_root = {_literal(alias)}\n", encoding="utf-8"
    )
    with pytest.raises(LocalConfigError, match="link/reparse"):
        load_local_config(tmp_path)


def test_ci_config_overrides_machine_local_bindings(tmp_path, monkeypatch):
    local_llvm = tmp_path / "local-llvm"
    ci_llvm = tmp_path / "ci-llvm"
    local_bundle = tmp_path / "local-bundle"
    ci_bundle = tmp_path / "ci-bundle"
    for path in (local_llvm, ci_llvm, local_bundle, ci_bundle):
        path.mkdir()
    (tmp_path / ".art-build.local.toml").write_text(
        "[tools]\n"
        f"llvm_root = {_literal(local_llvm)}\n"
        '[targets."windows-x86_64-msvc"]\n'
        f"bundle_root = {_literal(local_bundle)}\n",
        encoding="utf-8",
    )
    ci_config = tmp_path / "ci.toml"
    ci_config.write_text(
        "[tools]\n"
        f"llvm_root = {_literal(ci_llvm)}\n"
        '[targets."windows-x86_64-msvc"]\n'
        f"bundle_root = {_literal(ci_bundle)}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(CI_CONFIG_ENV, str(ci_config))

    config = load_local_config(tmp_path)

    assert config.source_file == ci_config
    assert config.tools["llvm_root"] == ci_llvm
    assert config.target_bindings("windows-x86_64-msvc")["bundle_root"] == ci_bundle


def test_ci_config_overrides_machine_local_target_runner(tmp_path, monkeypatch):
    local_runner = tmp_path / "local-qemu-aarch64"
    ci_runner = tmp_path / "ci-qemu-aarch64"
    local_runner.write_bytes(b"local")
    ci_runner.write_bytes(b"ci")
    (tmp_path / ".art-build.local.toml").write_text(
        '[target_runners]\n"linux-aarch64-gnu" = '
        f"{_literal(local_runner)}\n",
        encoding="utf-8",
    )
    ci_config = tmp_path / "ci.toml"
    ci_config.write_text(
        '[target_runners]\n"linux-aarch64-gnu" = '
        f"{_literal(ci_runner)}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(CI_CONFIG_ENV, str(ci_config))

    config = load_local_config(tmp_path)

    assert config.target_runners["linux-aarch64-gnu"] == ci_runner


def test_ci_config_path_must_be_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv(CI_CONFIG_ENV, "relative-ci.toml")
    with pytest.raises(LocalConfigError, match="absolute"):
        load_local_config(tmp_path)
