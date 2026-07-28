import java.io.*;
public class IoProbe {
  public static void main(String[] args) throws Exception {
    File dir = new File("run/tmp_io");
    System.out.println("mkdir=" + dir.mkdirs() + " exists=" + dir.exists() + " isDir=" + dir.isDirectory());
    File f = new File(dir, "roundtrip.txt");
    String payload = "phase3-io-ok\n";
    try (FileOutputStream out = new FileOutputStream(f)) {
      out.write(payload.getBytes("UTF-8"));
    }
    System.out.println("wrote len=" + f.length() + " path=" + f.getPath());
    byte[] buf = new byte[64];
    int n;
    try (FileInputStream in = new FileInputStream(f)) {
      n = in.read(buf);
    }
    String got = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
    System.out.println("read n=" + n + " got=" + got.replace("\n","\\n"));
    System.out.println("match=" + payload.equals(got));
    // mixed path write
    File mixed = new File("run/tmp_io/mixed\\slash.txt".replace('\\','/')); // ensure
    mixed = new File("run/tmp_io/mix_dir");
    mixed.mkdirs();
    File m = new File("run/tmp_io/mix_dir/a/b".replace('/','\\')); // windows-ish relative
    // relative mixed separators
    File m2 = new File("run/tmp_io/mix_dir\\nested/file.txt");
    System.out.println("mixedPath=" + m2.getPath() + " abs=" + m2.isAbsolute());
    m2.getParentFile().mkdirs();
    try (FileOutputStream out = new FileOutputStream(m2)) {
      out.write("mixed-ok".getBytes("UTF-8"));
    }
    try (FileInputStream in = new FileInputStream(m2)) {
      n = in.read(buf);
    }
    System.out.println("mixedRead=" + new String(buf,0,Math.max(n,0),"UTF-8"));
    // rename/delete via File API
    File ren = new File(dir, "renamed.txt");
    boolean renamed = f.renameTo(ren);
    System.out.println("rename=" + renamed + " renExists=" + ren.exists() + " oldExists=" + f.exists());
    boolean del = ren.delete();
    System.out.println("delete=" + del + " after=" + ren.exists());
    System.out.println("IoProbe.done=ok");
  }
}
