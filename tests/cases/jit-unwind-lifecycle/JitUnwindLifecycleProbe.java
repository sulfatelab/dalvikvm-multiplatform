import java.lang.reflect.Method;

public class JitUnwindLifecycleProbe {
  private static native boolean nativeRun(Method method);

  private static int target(int value) {
    int mixed = (value * 33) ^ 0x5a5a;
    return mixed + Integer.rotateLeft(value, 7);
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("jitunwindlifecycleprobe");
    Method target = JitUnwindLifecycleProbe.class.getDeclaredMethod("target", int.class);
    if (!nativeRun(target)) {
      throw new AssertionError("native lifecycle probe returned false");
    }
    int actual = target(12345);
    int expected = ((12345 * 33) ^ 0x5a5a) + Integer.rotateLeft(12345, 7);
    if (actual != expected) {
      throw new AssertionError("recompiled target returned " + actual + ", expected " + expected);
    }
    System.out.println("JitUnwindLifecycleProbe OK result=" + actual);
  }
}
