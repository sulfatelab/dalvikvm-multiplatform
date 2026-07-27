/** Phase 4 A8 native crash path: PE native AV; expects abort (non-zero), not silent success. */
public class CrashNativeProbe {
  private static native void nativeSegfault();

  private static final int OSR_COUNT = 2_000_000;
  private static int state;
  private static volatile Object sink;

  private static void jitCrashCaller(int value) {
    state = (state * 1664525) + value + 1013904223;
    nativeSegfault();
    state ^= state >>> 13;
  }

  private static long osrCrashLoop(int count) {
    Object[] retained = new Object[256];
    long checksum = 0;
    for (int i = 0; i < count; ++i) {
      checksum += ((i * 17L) ^ (i >>> 3)) & 0xffffL;
      if ((i & 255) == 0) {
        byte[] block = new byte[64 + (i & 31)];
        block[0] = (byte) i;
        retained[(i >>> 8) & 255] = block;
      }
      if (i + 1 == count) {
        sink = retained;
        state = (int) checksum;
        nativeSegfault();
      }
    }
    return checksum;
  }

  public static void main(String[] args) {
    System.out.println("CrashNativeProbe.start");
    System.out.flush();
    if (args.length != 0 && args[0].equals("jit")) {
      final int warmupCalls = 20000;
      for (int i = 0; i < warmupCalls; ++i) {
        jitCrashCaller(i);
      }
      try {
        Thread.sleep(250);
      } catch (InterruptedException e) {
        throw new AssertionError(e);
      }
      System.out.println(
          "CrashNativeProbe.jit_ready calls=" + warmupCalls + " state=" + state);
      System.out.flush();
      jitCrashCaller(warmupCalls);
    } else if (args.length != 0 && args[0].equals("osr")) {
      System.out.println("CrashNativeProbe.osr_armed count=" + OSR_COUNT);
      System.out.flush();
      long checksum = osrCrashLoop(OSR_COUNT);
      System.out.println(
          "CrashNativeProbe.osr_unexpected_return checksum=" + checksum
              + " state=" + state + " sink=" + sink);
    } else {
      nativeSegfault();
    }
    System.out.println("CrashNativeProbe.unexpected_continue");
    System.exit(2);
  }
}
