import java.lang.reflect.Method;

public class W025JitLifecycleStressProbe {
  private static native boolean nativeRun(Method[] managedMethods, Method[] nativeMethods,
                                          int cycles);

  private static native int nativeI(int value);
  private static native long nativeJ(long value);
  private static native double nativeD(double left, double right);
  private static native float nativeF(float value, int scale);
  private static native boolean nativeZ(boolean value);
  private static native Object nativeL(Object value);
  private static native long nativeMix(int i, long j, double d, Object value);
  private static native void nativeV(int[] values, int index);

  private static int target00(int value) { return value + 1; }
  private static int target01(int value) { return value * 3 + 7; }
  private static int target02(int value) { return (value ^ 0x55aa) + 2; }
  private static int target03(int value) { return Integer.rotateLeft(value, 3) - 9; }
  private static int target04(int value) { return value * value + 11; }
  private static int target05(int value) { return (value >>> 2) + value * 5; }
  private static int target06(int value) { return (value | 0x1234) - 13; }
  private static int target07(int value) { return Integer.reverseBytes(value) ^ 0x77; }
  private static int target08(int value) { return value * 17 - (value >>> 3); }
  private static int target09(int value) { return Integer.rotateRight(value ^ 0x2345, 5); }
  private static int target10(int value) { return (value & 0x7fff) * 19 + 23; }
  private static int target11(int value) { return (value << 4) ^ (value * 29); }
  private static int target12(int value) { return Integer.bitCount(value) + value * 31; }
  private static int target13(int value) { return (value % 97) * 37 - 5; }
  private static int target14(int value) { return Integer.highestOneBit(value) + value * 41; }
  private static int target15(int value) { return Integer.lowestOneBit(value) ^ (value * 43); }

  private static Method[] managedMethods() throws Exception {
    Method[] methods = new Method[16];
    for (int index = 0; index < methods.length; ++index) {
      methods[index] = W025JitLifecycleStressProbe.class.getDeclaredMethod(
          String.format("target%02d", index), int.class);
    }
    return methods;
  }

  private static Method[] nativeMethods() throws Exception {
    return new Method[] {
      W025JitLifecycleStressProbe.class.getDeclaredMethod("nativeI", int.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod("nativeJ", long.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod(
          "nativeD", double.class, double.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod(
          "nativeF", float.class, int.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod("nativeZ", boolean.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod("nativeL", Object.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod(
          "nativeMix", int.class, long.class, double.class, Object.class),
      W025JitLifecycleStressProbe.class.getDeclaredMethod(
          "nativeV", int[].class, int.class),
    };
  }

  private static int managedChecksum(int value) {
    return target00(value) ^ target01(value + 1) ^ target02(value + 2) ^
        target03(value + 3) ^ target04(value + 4) ^ target05(value + 5) ^
        target06(value + 6) ^ target07(value + 7) ^ target08(value + 8) ^
        target09(value + 9) ^ target10(value + 10) ^ target11(value + 11) ^
        target12(value + 12) ^ target13(value + 13) ^ target14(value + 14) ^
        target15(value + 15);
  }

  private static void verifyNativeMethods() {
    int i = nativeI(17);
    long j = nativeJ(1000L);
    double d = nativeD(1.25, 2.5);
    float f = nativeF(1.5f, 4);
    boolean z = nativeZ(false);
    if (i != 52 || j != 0x1234L + 1000L ||
        Double.doubleToLongBits(d) != Double.doubleToLongBits(6.25) ||
        Float.floatToIntBits(f) != Float.floatToIntBits(6.5f) || !z) {
      throw new AssertionError("JNI lifecycle values are incorrect: i=" + i + " j=" + j +
          " d=" + d + " f=" + f + " z=" + z);
    }
    Object marker = new Object();
    if (nativeL(marker) != marker || nativeMix(3, 7L, 2.0, marker) != 2017L) {
      throw new AssertionError("JNI reference/mixed lifecycle values are incorrect");
    }
    int[] values = {1, 2, 3};
    nativeV(values, 1);
    if (values[1] != 0x5a5a) {
      throw new AssertionError("JNI array lifecycle value is incorrect");
    }
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w025jitlifecyclestressprobe");
    Method[] managed = managedMethods();
    Method[] natives = nativeMethods();
    int cycles = args.length == 0 ? 12 : Integer.parseInt(args[0]);
    if (!nativeRun(managed, natives, cycles)) {
      throw new AssertionError("native JIT lifecycle stress returned false");
    }
    int first = managedChecksum(123);
    int second = managedChecksum(123);
    if (first != second) {
      throw new AssertionError("managed lifecycle checksum is unstable");
    }
    verifyNativeMethods();
    System.out.println("W025JitLifecycleStressProbe PASS cycles=" + cycles +
        " managed_checksum=" + first + " jni_values=pass");
  }
}
