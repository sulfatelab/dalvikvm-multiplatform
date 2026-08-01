# Register the unified target-aware test catalog after the product graph and
# common target policy are complete. This common include is not an entry point.

option(ART_BUILD_TESTS "Define the unified target-aware ART test catalog" ON)
if(ART_BUILD_TESTS)
    include(CTest)
    add_subdirectory("${_repo}/tests" tests)
endif()
