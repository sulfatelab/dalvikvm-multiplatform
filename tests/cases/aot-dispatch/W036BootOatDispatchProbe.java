import java.lang.reflect.Method;

public final class W036BootOatDispatchProbe {
  private static volatile boolean workerReady;
  private static volatile boolean workerArmed;
  private static volatile int selectedMethod = -1;
  private static volatile Throwable workerFailure;

  private static native void nativeRegisterWorker();
  private static native int nativeArm(Method[] candidates);
  private static native boolean nativeVerify(Method selected);
  private static native void nativeCleanup();

  private static Method method(Class<?> owner, String name, Class<?>... parameters)
      throws ReflectiveOperationException {
    return owner.getDeclaredMethod(name, parameters);
  }

  private static Method[] candidates() throws ReflectiveOperationException {
    return new Method[] {
      method(Integer.class, "parseInt", String.class),
      method(Integer.class, "toString", int.class),
      method(Long.class, "parseLong", String.class),
      method(Math.class, "max", int.class, int.class),
    };
  }

  private static void invokeSelected(int selected) {
    switch (selected) {
      case 0:
        if (Integer.parseInt("123456") != 123456) {
          throw new AssertionError("Integer.parseInt returned an unexpected value");
        }
        return;
      case 1:
        if (!"654321".equals(Integer.toString(654321))) {
          throw new AssertionError("Integer.toString returned an unexpected value");
        }
        return;
      case 2:
        if (Long.parseLong("1234567890123") != 1234567890123L) {
          throw new AssertionError("Long.parseLong returned an unexpected value");
        }
        return;
      case 3:
        if (Math.max(17, 23) != 23) {
          throw new AssertionError("Math.max returned an unexpected value");
        }
        return;
      default:
        throw new AssertionError("native probe selected an unknown method index: " + selected);
    }
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w036aotdispatchprobe");
    Method[] methods = candidates();
    Thread worker = new Thread(
        () -> {
          try {
            nativeRegisterWorker();
            workerReady = true;
            while (!workerArmed) {
              Thread.onSpinWait();
            }
            invokeSelected(selectedMethod);
          } catch (Throwable failure) {
            workerFailure = failure;
            workerReady = true;
          }
        },
        "W036-boot-oat-dispatch");
    worker.start();

    while (!workerReady) {
      Thread.onSpinWait();
    }

    Throwable armFailure = null;
    try {
      selectedMethod = nativeArm(methods);
    } catch (Throwable failure) {
      armFailure = failure;
    } finally {
      workerArmed = true;
    }
    worker.join();

    if (armFailure != null) {
      nativeCleanup();
      throw new AssertionError("failed to arm ordinary boot-OAT dispatch", armFailure);
    }
    if (workerFailure != null) {
      nativeCleanup();
      throw new AssertionError("ordinary boot-OAT worker failed", workerFailure);
    }
    if (!nativeVerify(methods[selectedMethod])) {
      throw new AssertionError("native boot-OAT dispatch verification returned false");
    }
    System.out.println("W036BootOatDispatchProbe PASS dispatch=ordinary rx_pc=observed jit=disabled");
  }
}
