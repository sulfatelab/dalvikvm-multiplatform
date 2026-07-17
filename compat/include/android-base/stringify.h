/*
 * Copyright (C) 2025 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// MDVM compat shim (project-owned glue, bp2cmake_linux_scope.md 5.3).
//
// android-16.0.0_r4 art's libartbase/base/macros.h now #includes
// <android-base/stringify.h>, a header that did NOT exist in the archive's
// 2023-era system/libbase (which the project keeps archive-pinned for the
// foundational libs while art+libcore are bumped in vendor/). Rather than bump
// libbase wholesale, carry this tiny, dependency-free macro header here -- a
// verbatim copy of the upstream android-base/stringify.h. If/when libbase is
// bumped to a coherent A16 snapshot, drop this shim.
#pragma once

// Converts macro argument 'x' into a string constant without macro expansion.
// So QUOTE(EINVAL) would be "EINVAL".
#define QUOTE(x...) #x

// Converts macro argument 'x' into a string constant after macro expansion.
// So STRINGIFY(EINVAL) would be "22".
#define STRINGIFY(x...) QUOTE(x)
