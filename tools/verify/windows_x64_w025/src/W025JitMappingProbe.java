public final class W025JitMappingProbe {
  private static native boolean nativeAudit(long expectedCapacityBytes, boolean requireCfg);

  private static int target(int value) {
    int mixed = Integer.rotateLeft(value * 33, value & 15) ^ 0x5a5a5a5a;
    return mixed + (value >>> 3);
  }

  public static void main(String[] args) {
    if (args.length != 2) {
      throw new IllegalArgumentException("expected capacity MiB and CFG requirement");
    }
    long expectedCapacityBytes = Long.parseLong(args[0]) * 1024L * 1024L;
    boolean requireCfg = Boolean.parseBoolean(args[1]);

    System.loadLibrary("w025jitmappingprobe");

    int checksum = 0;
    for (int iteration = 0; iteration < 200000; ++iteration) {
      checksum ^= target(iteration);
    }
    if (!nativeAudit(expectedCapacityBytes, requireCfg)) {
      throw new AssertionError("native JIT mapping audit returned false");
    }

    System.out.println(
        "W025JitMappingProbe PASS capacity_bytes=" + expectedCapacityBytes
            + " require_cfg=" + requireCfg + " checksum=" + checksum);
  }
}
