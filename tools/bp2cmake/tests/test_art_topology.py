import copy

import pytest

from tools import check_art_topology


def _manifest(target_id, modules):
    return {
        "target": {"target_id": target_id},
        "modules": [
            {"aosp_name": name, "cmake_target": cmake, "kind": kind}
            for name, cmake, kind in modules
        ],
    }


def _contract():
    return {
        "schema_version": 1,
        "targets": {"linux": "linux-x86_64-gnu", "windows": "windows-x86_64-msvc"},
        "module_set_differences": {
            "linux_only": {},
            "windows_only": {},
        },
        "kind_differences": {
            "base": {
                "direct_consumers": ["art"],
                "linux": "shared",
                "windows": "static",
                "reason": "reviewed boundary",
            }
        },
    }


def test_topology_contract_accepts_only_declared_kind_delta():
    linux = _manifest(
        "linux-x86_64-gnu",
        [("base", "base", "shared"), ("art", "art", "shared")],
    )
    windows = _manifest(
        "windows-x86_64-msvc",
        [("base", "base", "static"), ("art", "art", "shared")],
    )
    for manifest in (linux, windows):
        manifest["modules"][1]["link_dependencies"] = ["base"]
    result = check_art_topology.compare_topologies(linux, windows, _contract())
    assert result == {
        "linux_modules": 2,
        "windows_modules": 2,
        "set_differences": 0,
        "kind_differences": 1,
    }


def test_topology_contract_enforces_exact_kind_difference_consumers():
    linux = _manifest(
        "linux-x86_64-gnu",
        [("base", "base", "shared"), ("art", "art", "shared")],
    )
    windows = _manifest(
        "windows-x86_64-msvc",
        [("base", "base", "static"), ("art", "art", "shared")],
    )
    contract = _contract()
    for manifest in (linux, windows):
        manifest["modules"][1]["link_dependencies"] = ["base"]

    check_art_topology.compare_topologies(linux, windows, contract)
    windows["modules"][1]["link_dependencies"] = []
    with pytest.raises(check_art_topology.TopologyError, match="direct consumers"):
        check_art_topology.compare_topologies(linux, windows, contract)


def test_topology_contract_rejects_new_module_and_target_rename():
    linux = _manifest(
        "linux-x86_64-gnu",
        [("base", "base", "shared"), ("new", "new", "static")],
    )
    windows = _manifest(
        "windows-x86_64-msvc",
        [("base", "base", "static")],
    )
    with pytest.raises(check_art_topology.TopologyError, match="Linux-only"):
        check_art_topology.compare_topologies(linux, windows, _contract())

    renamed = copy.deepcopy(windows)
    renamed["modules"].append(
        {"aosp_name": "new", "cmake_target": "renamed", "kind": "static"}
    )
    contract = _contract()
    contract["kind_differences"]["new"] = {
        "linux": "static",
        "windows": "static",
        "reason": "not a real kind difference",
    }
    with pytest.raises(check_art_topology.TopologyError, match="CMake target names"):
        check_art_topology.compare_topologies(linux, renamed, contract)
