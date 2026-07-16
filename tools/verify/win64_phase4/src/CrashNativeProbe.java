/** Phase 4 A8 native crash path: PE native AV; expects abort (non-zero), not silent success. */
public class CrashNativeProbe {
  private static native void nativeSegfault();
  public static void main(String[] args) {
    System.out.println("CrashNativeProbe.start");
    System.out.flush();
    nativeSegfault();
    System.out.println("CrashNativeProbe.unexpected_continue");
    System.exit(2);
  }
}
