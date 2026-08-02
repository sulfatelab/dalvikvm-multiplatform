import argparse
from pathlib import Path
import subprocess
import zipfile

import pytest

from tests.support import managed_artifact


def _arguments(tmp_path: Path) -> argparse.Namespace:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "Probe.java"
    source.write_text("public class Probe {}\n", encoding="utf-8")
    jdk = tmp_path / "jdk-21"
    (jdk / "bin").mkdir(parents=True)
    (jdk / "bin" / "java").write_bytes(b"")
    (jdk / "bin" / "javac").write_bytes(b"")
    r8 = source_root / "vendor" / "r8" / "r8.jar"
    r8.parent.mkdir(parents=True)
    r8.write_bytes(b"r8")
    return argparse.Namespace(
        jdk_root=jdk,
        r8_jar=r8,
        source_root=source_root,
        output_root=tmp_path / "out" / "windows-x86_64-msvc" / "tests" / "managed",
        name="probe",
        source=[source],
        source_tree=[],
        exclude=[],
        aconfig=[],
        resource=[],
        boot_classpath=None,
        patch_module=None,
        javac_option=[],
        android_platform_build=False,
    )


def _successful_tool_run(commands):
    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[-1] == "-version":
            version = (
                'openjdk version "21.0.11"\n'
                if Path(command[0]).name == "java"
                else "javac 21.0.11\n"
            )
            return subprocess.CompletedProcess(command, 0, version, "")
        if Path(command[0]).name == "javac":
            classes = Path(command[command.index("-d") + 1])
            (classes / "Probe.class").write_bytes(b"class bytes")
        else:
            dex = Path(command[command.index("--output") + 1])
            (dex / "classes.dex").write_bytes(b"dex bytes")
        return subprocess.CompletedProcess(command, 0, "", "")

    return run


def test_probe_build_is_shell_free_deterministic_and_source_relative(tmp_path, monkeypatch):
    args = _arguments(tmp_path)
    commands = []
    monkeypatch.setattr(
        managed_artifact.subprocess, "run", _successful_tool_run(commands)
    )

    jar, manifest = managed_artifact.build_managed_artifact(args)
    first = jar.read_bytes()
    managed_artifact.build_managed_artifact(args)

    assert jar.read_bytes() == first
    with zipfile.ZipFile(jar) as archive:
        assert archive.namelist() == ["classes.dex"]
        assert archive.getinfo("classes.dex").date_time == (1980, 1, 1, 0, 0, 0)
    manifest_text = manifest.read_text(encoding="utf-8")
    assert '"sources": [\n    "source/Probe.java"\n  ]' in manifest_text
    assert str(tmp_path) not in manifest_text
    assert all(call[1]["shell"] is False for call in commands)
    assert any(str(call[0][-1]).startswith("@") for call in commands)


def test_resource_is_deterministic_portable_and_rejects_dex_collision(
    tmp_path, monkeypatch
):
    args = _arguments(tmp_path)
    resource = args.source_root / "security.properties"
    resource.write_text("security.provider.1=Probe\n", encoding="utf-8")
    args.resource = [[str(resource), "java/security/security.properties"]]
    monkeypatch.setattr(
        managed_artifact.subprocess, "run", _successful_tool_run([])
    )

    jar, manifest = managed_artifact.build_managed_artifact(args)
    with zipfile.ZipFile(jar) as archive:
        assert archive.namelist() == [
            "classes.dex",
            "java/security/security.properties",
        ]
        assert archive.read("java/security/security.properties") == resource.read_bytes()
    manifest_text = manifest.read_text(encoding="utf-8")
    assert "source/security.properties" in manifest_text
    assert str(tmp_path) not in manifest_text

    args.resource = [[str(resource), "classes.dex"]]
    with pytest.raises(managed_artifact.ManagedArtifactError, match="collides"):
        managed_artifact.build_managed_artifact(args)


def test_d8_failure_is_propagated_with_log_path(tmp_path, monkeypatch):
    args = _arguments(tmp_path)

    def run(command, **kwargs):
        if command[-1] == "-version":
            version = (
                'openjdk version "21.0.11"\n'
                if Path(command[0]).name == "java"
                else "javac 21.0.11\n"
            )
            return subprocess.CompletedProcess(command, 0, version, "")
        if Path(command[0]).name == "javac":
            classes = Path(command[command.index("-d") + 1])
            (classes / "Probe.class").write_bytes(b"class bytes")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 7, "", "D8 failed")

    monkeypatch.setattr(managed_artifact.subprocess, "run", run)
    with pytest.raises(managed_artifact.ManagedArtifactError, match="exit code 7"):
        managed_artifact.build_managed_artifact(args)
    assert (args.output_root / "logs" / "probe.d8.log").is_file()


def test_work_directory_must_be_below_managed_output_root(tmp_path):
    with pytest.raises(managed_artifact.ManagedArtifactError, match="escapes"):
        managed_artifact._replace_directory(tmp_path / "escape", tmp_path / "out")
    with pytest.raises(managed_artifact.ManagedArtifactError, match="escapes"):
        managed_artifact._replace_directory(
            tmp_path / "out" / ".." / "escape", tmp_path / "out"
        )


def test_java_argfile_quotes_windows_paths_without_a_shell(tmp_path):
    argfile = tmp_path / "sources.args"
    managed_artifact._write_java_argfile(
        argfile, [Path(r"C:\art source\Probe.java")]
    )
    assert argfile.read_text(encoding="utf-8") == (
        '"C:\\\\art source\\\\Probe.java"\n'
    )


def test_source_tree_rejects_symlink_entries(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "Probe.java"
    target.write_text("class Probe {}\n", encoding="utf-8")
    alias = tree / "Alias.java"
    try:
        alias.symlink_to(target.name)
    except OSError:
        pytest.skip("host cannot create a source symlink")
    with pytest.raises(managed_artifact.ManagedArtifactError, match="link/reparse"):
        managed_artifact._collect_java_sources(tree, [])


def test_stale_work_tree_rejects_nested_symlink(tmp_path):
    output = tmp_path / "out"
    work = output / "classes" / "probe"
    work.mkdir(parents=True)
    target = tmp_path / "outside"
    target.mkdir()
    try:
        (work / "alias").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create a stale work-tree symlink")
    with pytest.raises(managed_artifact.ManagedArtifactError, match="link/reparse"):
        managed_artifact._replace_directory(work, output)
