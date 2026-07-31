# Non-moving heap managed stress probe

`W013NonMovingStressProbe.java` is the managed half of the W-013 non-moving
allocator stress. The existing Windows x86-64 evidence covers low-address
non-moving arrays, allocation churn, forced collections, and address
stability. No other target is currently claimed.

The source is now compiled and D8-packaged by the unified target graph. Its
behavioral runtime gate remains separate from build verification until the
W-013 runner and result reviewer are migrated.
