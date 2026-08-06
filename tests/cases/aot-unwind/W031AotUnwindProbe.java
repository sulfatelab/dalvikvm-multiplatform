import java.lang.reflect.Method;

public class W031AotUnwindProbe {
  private static native boolean nativeAudit(Method[] managedMethods, Method[] nativeMethods);

  private static Method method(Class<?> owner, String name, Class<?>... parameters)
      throws ReflectiveOperationException {
    return owner.getDeclaredMethod(name, parameters);
  }

  private static Method[] managedMethods() throws ReflectiveOperationException {
    return new Method[] {
      method(String.class, "length"),
      method(String.class, "charAt", int.class),
      method(String.class, "indexOf", int.class),
      method(String.class, "isEmpty"),
      method(String.class, "substring", int.class),
      method(String.class, "equals", Object.class),
      method(Integer.class, "toString", int.class),
      method(Integer.class, "parseInt", String.class),
      method(Math.class, "abs", int.class),
      method(Math.class, "max", int.class, int.class),
    };
  }

  private static Method[] nativeMethods() throws ReflectiveOperationException {
    return new Method[] {
      method(System.class, "currentTimeMillis"),
      method(System.class, "nanoTime"),
      method(System.class, "arraycopy", Object.class, int.class, Object.class, int.class, int.class),
      method(Object.class, "getClass"),
      method(Object.class, "hashCode"),
      method(Object.class, "clone"),
      method(Thread.class, "currentThread"),
    };
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w031aotunwindprobe");
    String value = "windows-oat";
    if (value.length() != 11 || value.charAt(7) != '-' || System.nanoTime() == 0L) {
      throw new AssertionError("boot methods returned unexpected values");
    }
    if (!nativeAudit(managedMethods(), nativeMethods())) {
      throw new AssertionError("native AOT unwind audit returned false");
    }
    System.out.println("W031AotUnwindProbe PASS managed_call=pass jni_call=pass");
  }
}
