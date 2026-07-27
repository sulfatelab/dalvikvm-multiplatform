/** Phase 4 A8 native crash path: PE native AV; expects abort (non-zero), not silent success. */
public class CrashNativeProbe {
  private static native void nativeSegfault();

  private static int state;

  private static void jitCrashCaller(int value) {
    state = (state * 1664525) + value + 1013904223;
    nativeSegfault();
    state ^= state >>> 13;
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
    } else {
      nativeSegfault();
    }
    System.out.println("CrashNativeProbe.unexpected_continue");
    System.exit(2);
  }
}
