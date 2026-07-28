/**
 * Phase 4 A8: uncaught exception path remains controlled (prints, nonzero exit).
 * Companion native null-crash is covered by crash_native gate separately.
 */
public class CrashAbortProbe {
  public static void main(String[] args) {
    System.out.println("CrashAbortProbe.start");
    System.out.flush();
    throw new RuntimeException("phase4-abort-ok");
  }
}
