#include <windows.h>

#include <cstdint>
#include <cstdio>

#include "cet_compat.h"

namespace {

using art::UserShadowStackPolicyAllowsArt;
using art::UserShadowStackPolicyDecision;
using art::UserShadowStackPolicyDecisionName;
using art::UserShadowStackPolicyObservation;

bool Expect(const char* name,
            const UserShadowStackPolicyObservation& observation,
            UserShadowStackPolicyDecision expected) {
  const UserShadowStackPolicyDecision actual =
      art::EvaluateUserShadowStackPolicy(observation);
  if (actual == expected) {
    return true;
  }
  std::fprintf(stderr,
               "WIN32_CET_POLICY_PROBE FAIL case=%s expected=%s actual=%s\n",
               name,
               UserShadowStackPolicyDecisionName(expected),
               UserShadowStackPolicyDecisionName(actual));
  return false;
}

}  // namespace

int main() {
  bool ok = true;
  ok &= Expect("disabled",
               {true, 19041u, true, 0u, ERROR_SUCCESS},
               UserShadowStackPolicyDecision::kDisabled);

  constexpr uint32_t kRejectedFlags[] = {
      1u << 0,   // EnableUserShadowStack.
      1u << 1,   // AuditUserShadowStack.
      1u << 2,   // SetContextIpValidation.
      1u << 3,   // AuditSetContextIpValidation.
      1u << 4,   // EnableUserShadowStackStrictMode.
      1u << 5,   // BlockNonCetBinaries (compatibility-policy family).
      1u << 31,  // A future/reserved bit must also fail closed.
  };
  for (uint32_t flags : kRejectedFlags) {
    ok &= Expect("nonzero-flags",
                 {true, 19041u, true, flags, ERROR_SUCCESS},
                 UserShadowStackPolicyDecision::kEnabledOrAudited);
  }

  ok &= Expect("old-unavailable",
               {true, 18363u, false, 0u, ERROR_INVALID_PARAMETER},
               UserShadowStackPolicyDecision::kUnavailableOnOlderWindows);
  ok &= Expect("old-unexpected-error",
               {true, 18363u, false, 0u, ERROR_NOT_SUPPORTED},
               UserShadowStackPolicyDecision::kUnexpectedQueryFailure);
  ok &= Expect("new-query-failure",
               {true, 19041u, false, 0u, ERROR_INVALID_PARAMETER},
               UserShadowStackPolicyDecision::kUnexpectedQueryFailure);
  ok &= Expect("version-failure",
               {false, 0u, true, 0u, ERROR_SUCCESS},
               UserShadowStackPolicyDecision::kWindowsVersionUnavailable);
  if (!ok) {
    return 1;
  }

  const UserShadowStackPolicyObservation actual = art::QueryUserShadowStackPolicy();
  const UserShadowStackPolicyDecision decision =
      art::EvaluateUserShadowStackPolicy(actual);
  std::printf("WIN32_CET_POLICY_PROBE actual=%s build=%u flags=0x%08x error=%u\n",
              UserShadowStackPolicyDecisionName(decision),
              actual.windows_build_known ? actual.windows_build : 0u,
              actual.flags,
              actual.query_error);
  if (!UserShadowStackPolicyAllowsArt(decision)) {
    std::fprintf(stderr,
                 "WIN32_CET_POLICY_PROBE REJECT Hardware-enforced Stack Protection "
                 "must be completely disabled before process creation\n");
    return 2;
  }
  std::puts("WIN32_CET_POLICY_PROBE PASS");
  return 0;
}
