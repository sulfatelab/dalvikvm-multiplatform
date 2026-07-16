import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileNotFoundException;
import java.io.IOException;

/**
 * Broader Os/file errno + UTF-8 path smoke for Win64 PE.
 * Covers product-relevant open failures and non-ASCII path I/O.
 */
public class OsErrnoProbe {
  static int fails = 0;
  static void check(String name, boolean ok) {
    System.out.println((ok ? "PASS " : "FAIL ") + name);
    if (!ok) fails++;
  }

  public static void main(String[] args) throws Exception {
    File base = new File("run/tmp_os");
    check("mkdir", base.mkdirs() || base.isDirectory());

    // Missing file open should fail with FileNotFoundException (not crash)
    boolean missingOk = false;
    try {
      new FileInputStream(new File(base, "no_such_file_xyz.txt")).close();
    } catch (FileNotFoundException e) {
      missingOk = true;
      System.out.println("missing.err=" + e.getClass().getSimpleName());
    } catch (Throwable t) {
      System.out.println("missing.unexpected=" + t);
    }
    check("missing_open_fnfe", missingOk);

    // Directory-as-file write should fail on Windows (or at least not succeed silently)
    File dir = new File(base, "adir");
    dir.mkdirs();
    boolean dirWriteFail = false;
    try {
      new FileOutputStream(dir).close();
    } catch (IOException e) {
      dirWriteFail = true;
      System.out.println("dirWrite.err=" + e.getClass().getSimpleName() + ":" + e.getMessage());
    } catch (Throwable t) {
      System.out.println("dirWrite.unexpected=" + t);
    }
    check("dir_as_file_fails", dirWriteFail);

    // UTF-8 filename round-trip (NFC Chinese/umlaut)
    String name = "utf8_测试_äöü.txt";
    File uf = new File(base, name);
    byte[] payload = ("hello-" + name).getBytes("UTF-8");
    try (FileOutputStream out = new FileOutputStream(uf)) {
      out.write(payload);
    }
    check("utf8_exists", uf.exists());
    check("utf8_length", uf.length() == payload.length);
    byte[] buf = new byte[256];
    int n;
    try (FileInputStream in = new FileInputStream(uf)) {
      n = in.read(buf);
    }
    String got = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
    check("utf8_readback", got.equals("hello-" + name));
    System.out.println("utf8.path=" + uf.getPath());
    System.out.println("utf8.abs=" + uf.getAbsolutePath());

    // list includes utf8 name
    String[] kids = base.list();
    boolean listed = false;
    if (kids != null) {
      for (String k : kids) if (name.equals(k)) listed = true;
    }
    check("utf8_listed", listed);
    System.out.println("list.count=" + (kids == null ? -1 : kids.length));

    // rename + delete
    File ren = new File(base, "utf8_renamed.txt");
    check("rename", uf.renameTo(ren) && ren.exists());
    check("delete", ren.delete() && !ren.exists());

    System.out.println("OsErrnoProbe.fails=" + fails);
    System.out.println("OsErrnoProbe.done=ok");
    if (fails != 0) System.exit(1);
  }
}
