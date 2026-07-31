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

template <typename Setter>
bool ExpectPolicy(const char* name,
                  Setter setter,
                  UserShadowStackPolicyDecision expected) {
  PROCESS_MITIGATION_USER_SHADOW_STACK_POLICY policy = {};
  setter(&policy);
  return Expect(name,
                {true, 19041u, true, policy.Flags, ERROR_SUCCESS},
                expected);
}

template <typename Setter>
bool ExpectTestPolicyName(const char* name, Setter setter) {
  PROCESS_MITIGATION_USER_SHADOW_STACK_POLICY expected = {};
  setter(&expected);
  uint32_t actual = 0u;
  if (art::ParseTestUserShadowStackPolicy(name, &actual) && actual == expected.Flags) {
    return true;
  }
  std::fprintf(stderr,
               "WIN32_CET_POLICY_PROBE FAIL test-policy=%s expected=0x%08x "
               "actual=0x%08x\n",
               name,
               expected.Flags,
               actual);
  return false;
}

}  // namespace

int main() {
  bool ok = true;
  ok &= Expect("disabled",
               {true, 19041u, true, 0u, ERROR_SUCCESS},
               UserShadowStackPolicyDecision::kDisabled);

  ok &= ExpectPolicy("enable-shadow-stack",
                     [](auto* policy) { policy->EnableUserShadowStack = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("audit-shadow-stack",
                     [](auto* policy) { policy->AuditUserShadowStack = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("context-ip-validation",
                     [](auto* policy) { policy->SetContextIpValidation = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("audit-context-ip-validation",
                     [](auto* policy) { policy->AuditSetContextIpValidation = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("strict-shadow-stack",
                     [](auto* policy) { policy->EnableUserShadowStackStrictMode = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("block-non-cet",
                     [](auto* policy) { policy->BlockNonCetBinaries = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("block-non-ehcont",
                     [](auto* policy) { policy->BlockNonCetBinariesNonEhcont = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("audit-block-non-cet",
                     [](auto* policy) { policy->AuditBlockNonCetBinaries = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);
  ok &= ExpectPolicy("relaxed-context-ip-validation",
                     [](auto* policy) { policy->SetContextIpValidationRelaxedMode = 1; },
                     UserShadowStackPolicyDecision::kIncompatible);

  ok &= ExpectTestPolicyName(
      "enable-user-shadow-stack", [](auto* policy) { policy->EnableUserShadowStack = 1; });
  ok &= ExpectTestPolicyName(
      "audit-user-shadow-stack", [](auto* policy) { policy->AuditUserShadowStack = 1; });
  ok &= ExpectTestPolicyName(
      "set-context-ip-validation", [](auto* policy) { policy->SetContextIpValidation = 1; });
  ok &= ExpectTestPolicyName("audit-set-context-ip-validation",
                             [](auto* policy) { policy->AuditSetContextIpValidation = 1; });
  ok &= ExpectTestPolicyName("strict-user-shadow-stack",
                             [](auto* policy) { policy->EnableUserShadowStackStrictMode = 1; });
  ok &= ExpectTestPolicyName(
      "block-non-cet-binaries", [](auto* policy) { policy->BlockNonCetBinaries = 1; });
  ok &= ExpectTestPolicyName("block-non-cet-binaries-non-ehcont",
                             [](auto* policy) { policy->BlockNonCetBinariesNonEhcont = 1; });
  ok &= ExpectTestPolicyName("audit-block-non-cet-binaries",
                             [](auto* policy) { policy->AuditBlockNonCetBinaries = 1; });
  ok &= ExpectTestPolicyName("relaxed-context-ip-validation",
                             [](auto* policy) { policy->SetContextIpValidationRelaxedMode = 1; });

  ok &= ExpectPolicy("dynamic-api-out-of-process-only",
                     [](auto* policy) { policy->CetDynamicApisOutOfProcOnly = 1; },
                     UserShadowStackPolicyDecision::kDisabled);
  ok &= ExpectPolicy("reserved-low",
                     [](auto* policy) { policy->ReservedFlags = 1; },
                     UserShadowStackPolicyDecision::kDisabled);
  ok &= ExpectPolicy("reserved-high",
                     [](auto* policy) { policy->ReservedFlags = 1u << 21; },
                     UserShadowStackPolicyDecision::kDisabled);
  ok &= ExpectPolicy("safe-known-plus-reserved",
                     [](auto* policy) {
                       policy->CetDynamicApisOutOfProcOnly = 1;
                       policy->ReservedFlags = (1u << 22) - 1u;
                     },
                     UserShadowStackPolicyDecision::kDisabled);
  ok &= ExpectPolicy("incompatible-plus-safe-and-reserved",
                     [](auto* policy) {
                       policy->EnableUserShadowStack = 1;
                       policy->CetDynamicApisOutOfProcOnly = 1;
                       policy->ReservedFlags = (1u << 22) - 1u;
                     },
                     UserShadowStackPolicyDecision::kIncompatible);

  ok &= ExpectTestPolicyName("dynamic-apis-out-of-proc-only",
                             [](auto* policy) { policy->CetDynamicApisOutOfProcOnly = 1; });
  ok &= ExpectTestPolicyName(
      "reserved-low", [](auto* policy) { policy->ReservedFlags = 1u; });
  ok &= ExpectTestPolicyName(
      "reserved-high", [](auto* policy) { policy->ReservedFlags = 1u << 21; });
  ok &= ExpectTestPolicyName(
      "reserved-all", [](auto* policy) { policy->ReservedFlags = (1u << 22) - 1u; });
  uint32_t invalid_test_flags = 0u;
  if (art::ParseTestUserShadowStackPolicy("unknown-policy", &invalid_test_flags)) {
    std::fputs("WIN32_CET_POLICY_PROBE FAIL accepted unknown test policy\n", stderr);
    ok = false;
  }
  UserShadowStackPolicyObservation invalid_test_input = {
      true, 19041u, true, 0u, ERROR_SUCCESS};
  invalid_test_input.test_policy_forced = true;
  invalid_test_input.test_policy_input_valid = false;
  ok &= Expect("invalid-test-policy",
               invalid_test_input,
               UserShadowStackPolicyDecision::kUnexpectedQueryFailure);

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
  const uint32_t known_incompatible =
      art::KnownIncompatibleUserShadowStackPolicyFlags(actual.flags);
  std::printf("WIN32_CET_POLICY_PROBE actual=%s build=%u flags=0x%08x "
              "known_incompatible=0x%08x error=%u\n",
              UserShadowStackPolicyDecisionName(decision),
              actual.windows_build_known ? actual.windows_build : 0u,
              actual.flags,
              known_incompatible,
              actual.query_error);
  if (!UserShadowStackPolicyAllowsArt(decision)) {
    std::fprintf(stderr,
                 "WIN32_CET_POLICY_PROBE REJECT incompatible CET user-shadow-stack "
                 "policy fields must be disabled before process creation\n");
    return 2;
  }
  std::puts("WIN32_CET_POLICY_PROBE PASS");
  return 0;
}
