# Exact target-applicability policy for the unified ART test catalog.
#
# Keep each independently admitted probe on its own named selector even when
# multiple selectors currently contain the same target IDs. A future target
# admission must update only the probe whose behavioral contract was reviewed.

include_guard(DIRECTORY)

set(_art_windows_current_selector
    PLATFORMS windows TARGET_ARCHES x86_64 TARGET_ABIS msvc)
set(_art_windows_x86_64_msvc_selector
    TARGET_IDS windows-x86_64-msvc)
set(_art_linux_x86_64_gnu_selector
    TARGET_IDS linux-x86_64-gnu)
set(_art_linux_runtime_smoke_ids_selector
    TARGET_IDS linux-x86_64-gnu linux-aarch64-gnu)
set(_art_current_native_ids_selector
    TARGET_IDS linux-x86_64-gnu windows-x86_64-msvc)
set(_art_critical_native_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_native_abi_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_math_critical_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_gc_stress_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_handle_leak_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_core_probe_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_interrupt_probe_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_runtime_memory_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_perf_smoke_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_thread_heavy_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_non_moving_128m_ids_selector
    TARGET_IDS
        linux-x86_64-gnu
        linux-aarch64-gnu
        windows-x86_64-msvc)
set(_art_imageless_runtime_ids_selector
    TARGET_IDS linux-x86_64-gnu linux-aarch64-gnu windows-x86_64-msvc)
