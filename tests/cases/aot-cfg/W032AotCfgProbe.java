import java.lang.reflect.Method;

public class W032AotCfgProbe {
  private static native boolean nativeAudit(Method quickMethod,
                                            Method jniMethod);
  private static native boolean nativeAuditCorruption();

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w032aotcfgprobe");
    Method quickMethod = Math.class.getDeclaredMethod("abs", int.class);
    Method jniMethod = System.class.getDeclaredMethod("nanoTime");
    if (!nativeAudit(quickMethod, jniMethod)) {
      throw new AssertionError("native AOT CFG audit returned false");
    }
    if (!nativeAuditCorruption()) {
      throw new AssertionError(
          "native AOT CFG corruption audit returned false");
    }
    System.out.println("W032AotCfgProbe PASS");
  }
}
