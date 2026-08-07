import java.lang.reflect.Method;
import java.util.Arrays;

public final class W037BootOatRelocationFaultGcProbe {
  private static final int GC_ROUNDS = 8;

  private static volatile long sink;

  private static native int nativeBegin(Method[] faultMethods, String imagePath);
  private static native boolean nativeVerify(
      Method selectedMethod, boolean faultCaught, int gcRounds);
  private static native void nativeCleanup();

  private static Method method(Class<?> owner, String name, Class<?>... parameters)
      throws ReflectiveOperationException {
    return owner.getDeclaredMethod(name, parameters);
  }

  private static Method[] faultMethods() throws ReflectiveOperationException {
    return new Method[] {
      method(Arrays.class, "sort", int[].class),
      method(Arrays.class, "fill", int[].class, int.class),
      method(Arrays.class, "binarySearch", int[].class, int.class),
      method(Arrays.class, "copyOf", int[].class, int.class),
    };
  }

  private static void primeBootMethods() {
    int[] values = {9, 3, 7, 1};
    Arrays.sort(values);
    Arrays.fill(values, 5);
    sink += Arrays.binarySearch(values, 5);
    sink += Arrays.copyOf(values, values.length + 1)[0];
  }

  private static void invokeNullFault(int selected) {
    switch (selected) {
      case 0:
        Arrays.sort((int[]) null);
        return;
      case 1:
        Arrays.fill((int[]) null, 7);
        return;
      case 2:
        Arrays.binarySearch((int[]) null, 7);
        return;
      case 3:
        Arrays.copyOf((int[]) null, 7);
        return;
      default:
        throw new AssertionError("native probe selected an unknown fault method: " + selected);
    }
  }

  private static void forceGcRounds() {
    byte[][] retained = new byte[128][];
    for (int round = 0; round < GC_ROUNDS; ++round) {
      for (int index = 0; index < 2048; ++index) {
        byte[] allocation = new byte[4096 + (index & 255)];
        allocation[0] = (byte) (round ^ index);
        allocation[allocation.length - 1] = (byte) index;
        sink += (allocation[0] & 0xff) + (allocation[allocation.length - 1] & 0xff);
        if ((index & 15) == 0) {
          retained[(index >> 4) & (retained.length - 1)] = allocation;
        }
      }
      System.gc();
    }
    for (byte[] allocation : retained) {
      if (allocation != null) {
        sink += (allocation[0] & 0xff) + (allocation[allocation.length - 1] & 0xff);
      }
    }
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w037aotexecutionprobe");
    primeBootMethods();
    Method[] methods = faultMethods();
    int selected = nativeBegin(methods, "runtime/boot-image/x86_64/boot.art");

    boolean caught = false;
    try {
      invokeNullFault(selected);
    } catch (NullPointerException expected) {
      caught = true;
      if (expected.getStackTrace().length == 0) {
        nativeCleanup();
        throw new AssertionError("managed boot-OAT fault has no Java stack trace", expected);
      }
    }
    if (!caught) {
      nativeCleanup();
      throw new AssertionError("selected boot-OAT method did not throw NullPointerException");
    }

    forceGcRounds();
    if (!nativeVerify(methods[selected], caught, GC_ROUNDS)) {
      throw new AssertionError("native relocation/fault/GC-root verification returned false");
    }
    System.out.println(
        "W037BootOatRelocationFaultGcProbe PASS "
            + "relocation=observed fault=recovered gc_roots=survived jit=disabled");
  }
}
