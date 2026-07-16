/** System properties + wall clock sanity for Win64 PE product. */
public class PropsProbe {
  public static void main(String[] args) throws Exception {
    String[] keys = {
      "java.version", "java.vm.version", "java.specification.version",
      "os.name", "os.arch", "file.separator", "path.separator",
      "line.separator", "user.dir", "user.home", "user.name", "file.encoding"
    };
    for (String k : keys) {
      String v = System.getProperty(k);
      System.out.println(k + "=" + (v == null ? "<null>" : v.replace("\r", "\\r").replace("\n", "\\n")));
    }
    // Reflect STATIC_PROPERTIES if accessible
    try {
      Class<?> c = Class.forName("java.lang.AndroidHardcodedSystemProperties");
      java.lang.reflect.Field f = c.getDeclaredField("JAVA_VERSION");
      f.setAccessible(true);
      System.out.println("hardcoded.JAVA_VERSION=" + f.get(null));
    } catch (Throwable t) {
      System.out.println("hardcoded.reflect=" + t);
    }
    long t0 = System.currentTimeMillis();
    long n0 = System.nanoTime();
    Thread.sleep(50);
    long t1 = System.currentTimeMillis();
    long n1 = System.nanoTime();
    long dt = t1 - t0;
    long dn = n1 - n0;
    System.out.println("millis.delta=" + dt);
    System.out.println("nanos.delta=" + dn);
    String jv = System.getProperty("java.version");
    boolean versionOk = "1.8.0".equals(jv);
    boolean ok =
        versionOk
            && "Windows".equals(System.getProperty("os.name"))
            && "\\".equals(System.getProperty("file.separator"))
            && ";".equals(System.getProperty("path.separator"))
            && System.getProperty("user.dir") != null
            && System.getProperty("user.home") != null
            && dt >= 20 && dt < 5000
            && dn >= 10_000_000L;
    System.out.println("java.version.nonzero=" + versionOk);
    System.out.println("props.ok=" + ok);
    System.out.println("PropsProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
