// Project-owned compat shim — NOT from AOSP.
//
// Several AOSP headers (e.g. libziparchive's zip_writer.h) #include
// <gtest/gtest_prod.h> purely for the FRIEND_TEST macro, which lets production
// classes grant friendship to not-yet-defined test fixtures. Upstream this
// header ships with googletest. We do not vendor googletest (we build no
// tests), so we provide the standalone macro here. This is the same
// "project-owned glue" pattern as native/jdwpheader/jdwpTransport.h.
//
// Source of truth: googletest's gtest/gtest_prod.h (BSD-3-Clause). Macro only.

#ifndef MDVM_COMPAT_GTEST_PROD_H_
#define MDVM_COMPAT_GTEST_PROD_H_

// Production code can declare:  FRIEND_TEST(FixtureName, TestName);
// to befriend the generated test class FixtureName_TestName_Test.
#define FRIEND_TEST(test_case_name, test_name) \
    friend class test_case_name##_##test_name##_Test

#endif  // MDVM_COMPAT_GTEST_PROD_H_
