import sys

from bp2cmake.capture_output import main


def test_capture_output_writes_child_stdout(tmp_path):
    output = tmp_path / "generated.txt"
    rc = main(
        [
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'generated\\n')",
        ]
    )
    assert rc == 0
    assert output.read_bytes() == b"generated\n"


def test_capture_output_preserves_unchanged_file(tmp_path):
    output = tmp_path / "generated.txt"
    output.write_bytes(b"same")
    before = output.stat().st_mtime_ns
    assert main(
        ["--output", str(output), "--", sys.executable, "-c", "print('same', end='')"]
    ) == 0
    assert output.stat().st_mtime_ns == before
