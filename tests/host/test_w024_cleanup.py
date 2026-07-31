import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_w024_cleanup_source_contract():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "support" / "w024_cleanup.py")],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip() == "W-024 cleanup source check: PASS"
