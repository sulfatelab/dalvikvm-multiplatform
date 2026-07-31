from pathlib import Path

import pytest

from bp2cmake.local_config import LocalConfigError, load_local_config


def _literal(path: Path) -> str:
    return "'" + str(path) + "'"


def test_absent_local_config_is_empty(tmp_path):
    config = load_local_config(tmp_path)
    assert config.source_file is None
    assert config.tools == {}
    assert config.targets == {}


def test_loads_valid_path_bindings(tmp_path):
    llvm = tmp_path / "llvm"
    bundle = tmp_path / "windows-bundle"
    llvm.mkdir()
    bundle.mkdir()
    output = tmp_path / "out-does-not-exist"
    (tmp_path / ".art-build.local.toml").write_text(
        "[tools]\n"
        f"llvm_root = {_literal(llvm)}\n"
        "[build]\n"
        f"output_root = {_literal(output)}\n"
        '[targets."windows-x86_64-msvc"]\n'
        f"bundle_root = {_literal(bundle)}\n",
        encoding="utf-8",
    )

    config = load_local_config(tmp_path)
    assert config.tools["llvm_root"] == llvm
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
