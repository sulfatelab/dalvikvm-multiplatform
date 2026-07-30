"""Single target-aware overlay entry point for the ART product graph.

The first migration step delegates to the reviewed Linux and Windows policy
datasets. Their module declarations can be composed into this file gradually
without changing the generator or public build frontend again.
"""

from pathlib import Path

from bp2cmake.overlay import Overlay, load_overlay
from bp2cmake.target import TargetProfile


def make_overlay(target: TargetProfile) -> Overlay:
    policy_dir = Path(__file__).parent
    if target.os_or_runtime == "linux":
        return load_overlay(str(policy_dir / "port_policy.py"))
    if target.os_or_runtime == "windows":
        return load_overlay(str(policy_dir / "port_policy_windows.py"))
    raise ValueError(f"no ART overlay policy for target {target.target_id!r}")
