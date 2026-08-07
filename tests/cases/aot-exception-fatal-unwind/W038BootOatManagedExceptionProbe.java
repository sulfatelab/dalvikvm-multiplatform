import java.lang.reflect.Method;

public final class W038BootOatManagedExceptionProbe {
  private static volatile long sink;

  private static native int nativeBegin(Method[] candidates);
  private static native boolean nativeVerify(Method selected, boolean caught, boolean traceTarget);

  private static Method method(Class<?> owner, String name, Class<?>... parameters)
      throws ReflectiveOperationException {
    return owner.getDeclaredMethod(name, parameters);
  }

  private static Method[] candidates() throws ReflectiveOperationException {
    return new Method[] {
      method(Integer.class, "parseInt", String.class),
      method(Long.class, "parseLong", String.class),
      method(Math.class, "addExact", int.class, int.class),
      method(Character.class, "toChars", int.class),
    };
  }

  private static void primeCandidates() {
    sink += Integer.parseInt("17");
    sink += Long.parseLong("23");
    sink += Math.addExact(29, 31);
    sink += Character.toChars('A')[0];
  }

  private static Class<? extends RuntimeException> invokeInvalid(int selected) {
    switch (selected) {
      case 0:
        Integer.parseInt("w038-not-an-integer");
        return NumberFormatException.class;
      case 1:
        Long.parseLong("w038-not-a-long");
        return NumberFormatException.class;
      case 2:
        Math.addExact(Integer.MAX_VALUE, 1);
        return ArithmeticException.class;
      case 3:
        Character.toChars(0x110000);
        return IllegalArgumentException.class;
      default:
        throw new AssertionError("native probe selected an unknown exception method: " + selected);
    }
  }

  private static boolean traceContains(StackTraceElement[] trace, Method selected) {
    String owner = selected.getDeclaringClass().getName();
    String name = selected.getName();
    for (StackTraceElement frame : trace) {
      if (owner.equals(frame.getClassName()) && name.equals(frame.getMethodName())) {
        return true;
      }
    }
    return false;
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w038aotunwindprobe");
    primeCandidates();
    Method[] methods = candidates();
    int selected = nativeBegin(methods);

    RuntimeException caught = null;
    Class<? extends RuntimeException> expected = null;
    try {
      expected = invokeInvalid(selected);
    } catch (RuntimeException exception) {
      caught = exception;
    }
    if (caught == null) {
      throw new AssertionError("selected boot-OAT method did not throw");
    }
    if (expected == null) {
      expected = selected < 2 ? NumberFormatException.class
          : selected == 2 ? ArithmeticException.class : IllegalArgumentException.class;
    }
    if (!expected.isInstance(caught)) {
      throw new AssertionError("selected method threw " + caught.getClass().getName(), caught);
    }
    StackTraceElement[] trace = caught.getStackTrace();
    boolean traceTarget = trace.length != 0 && traceContains(trace, methods[selected]);
    if (!nativeVerify(methods[selected], true, traceTarget)) {
      throw new AssertionError("native explicit-exception verification returned false");
    }
    System.out.println(
        "W038BootOatManagedExceptionProbe PASS exception=caught trace=target "
            + "entry=oat jit=disabled");
  }
}
