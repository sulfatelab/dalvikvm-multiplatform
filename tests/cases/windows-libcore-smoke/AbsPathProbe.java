import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;

/**
 * Option H absolute-path / classpath acceptance (P2–P5, P8–P9c) under wine64.
 * Expects hello.jar staged at C:\art_phase3\abs_dir\hello.jar (wine drive_c).
 */
public class AbsPathProbe {
  static int fails = 0;
  static void check(String name, boolean ok) {
    System.out.println((ok ? "PASS " : "FAIL ") + name);
    if (!ok) fails++;
  }

  public static void main(String[] args) throws Exception {
    System.out.println("path.separator=" + System.getProperty("path.separator"));
    System.out.println("file.separator=" + System.getProperty("file.separator"));
    System.out.println("java.class.path=" + System.getProperty("java.class.path"));

    // P5 parent/name
    File f = new File("C:\\a\\b\\c.txt");
    check("P5_parent", "C:\\a\\b".equals(f.getParent()) || "C:\\a\\b".equals(f.getParentFile().getPath()));
    check("P5_name", "c.txt".equals(f.getName()));

    // P5c relative absolute form
    File rel = new File("rel/path/x");
    String absRel = rel.getAbsolutePath();
    System.out.println("P5c_abs=" + absRel);
    check("P5c_has_drive_or_root", absRel.length() > 2 && (absRel.charAt(1) == ':' || absRel.startsWith("\\\\")));
    check("P5c_backslash_style", absRel.indexOf('/') < 0 || absRel.indexOf('\\') >= 0);

    // P5b parent dots
    File up = new File("..\\file.txt");
    String absUp = up.getAbsolutePath();
    System.out.println("P5b_abs=" + absUp);
    check("P5b_not_posix_root", !absUp.startsWith("/file") && !absUp.startsWith("//?/"));

    // P2–P4 style File absolute math
    String[] absSamples = {
      "C:\\art_phase3\\abs_dir\\hello.jar",
      "C:/art_phase3/abs_dir/hello.jar",
      "C:\\art_phase3\\abs_dir/hello.jar"
    };
    for (String s : absSamples) {
      File af = new File(s);
      check("abs_isAbsolute:" + s, af.isAbsolute());
      check("abs_exists:" + s, af.exists());
      check("abs_isFile:" + s, af.isFile());
      check("abs_length:" + s, af.length() > 0);
      System.out.println("path=" + af.getPath() + " len=" + af.length());
    }

    // P7-ish roundtrip under C:
    File tmpDir = new File("C:\\art_phase3\\tmp_io");
    check("mkdir_c", tmpDir.mkdirs() || tmpDir.isDirectory());
    File tmp = new File(tmpDir, "round.txt");
    byte[] payload = "abs-io-ok".getBytes("UTF-8");
    try (FileOutputStream out = new FileOutputStream(tmp)) { out.write(payload); }
    byte[] buf = new byte[32];
    int n;
    try (FileInputStream in = new FileInputStream(tmp)) { n = in.read(buf); }
    String got = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
    check("P7_c_roundtrip", "abs-io-ok".equals(got));
    tmp.delete();

    // Classpath: Hello must be loadable from absolute cp when staged (runner sets -cp)
    try {
      Class.forName("Hello");
      System.out.println("Hello.load=ok");
      check("Hello.load", true);
    } catch (Throwable t) {
      System.out.println("Hello.load=" + t);
      check("Hello.load", false);
    }

    // Runtime memory (A4 adjacent)
    Runtime rt = Runtime.getRuntime();
    long free = rt.freeMemory(), total = rt.totalMemory(), max = rt.maxMemory();
    System.out.println("mem free=" + free + " total=" + total + " max=" + max);
    check("Runtime.maxMemory>0", max > 0);
    check("Runtime.totalMemory>=0", total >= 0);
    check("Runtime.freeMemory>=0", free >= 0);
    check("Runtime.max>=total", max >= total);

    System.out.println("AbsPathProbe.fails=" + fails);
    System.out.println("AbsPathProbe.done=ok");
    if (fails != 0) System.exit(1);
  }
}
