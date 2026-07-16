/**
 * Win64 Option H path/classpath probe for imageless ART under wine64/host.
 *
 * Build (dex jar):
 *   tools/verify/win64_phase3/build_probe.sh
 * Run:
 *   tools/verify/win64_phase3/run_probe.sh
 *
 * Pass criteria (stdout):
 *   path.separator=;
 *   File.fs=java.io.WinNTFileSystem
 *   isAbsolute=true for C:\... and mixed C:\a/b
 *   UNC kept as \\server\share\...
 *   multi-jar java.class.path contains ';'
 *   Hello.load=ok when hello.jar is on -cp
 */
public class PathProbe {
  public static void main(String[] args) throws Exception {
    System.out.println("file.separator=" + System.getProperty("file.separator"));
    System.out.println("path.separator=" + System.getProperty("path.separator"));
    System.out.println("java.class.path=" + System.getProperty("java.class.path"));
    System.out.println("File.pathSeparator=" + java.io.File.pathSeparator);
    System.out.println("File.separator=" + java.io.File.separator);
    System.out.println("user.dir=" + System.getProperty("user.dir"));
    System.out.println("isLetterC=" + Character.isLetter('C'));

    java.lang.reflect.Field fsField = java.io.File.class.getDeclaredField("fs");
    fsField.setAccessible(true);
    Object fs = fsField.get(null);
    System.out.println("File.fs=" + (fs == null ? "null" : fs.getClass().getName()));

    java.lang.reflect.Field plField = java.io.File.class.getDeclaredField("prefixLength");
    plField.setAccessible(true);

    String[] samples = {
      "C:\\x",
      "C:/x",
      "C:\\User/admin/.ssh/x",
      "\\\\server\\share\\a",
      "\\foo",
      "rel/path",
      "file.txt",
      "../just/works.txt",
      "run/hello.jar"
    };
    for (String s : samples) {
      java.io.File f = new java.io.File(s);
      System.out.println("---");
      System.out.println("in=" + s);
      System.out.println("path=" + f.getPath());
      System.out.println("prefixLength=" + plField.getInt(f));
      System.out.println("isAbsolute=" + f.isAbsolute());
      System.out.println("abs=" + f.getAbsolutePath());
    }

    System.out.println("---");
    System.out.println("existsHello=" + new java.io.File("run/hello.jar").exists());
    try {
      Class.forName("Hello");
      System.out.println("Hello.load=ok");
    } catch (Throwable t) {
      System.out.println("Hello.load=" + t.getClass().getSimpleName() + ":" + t.getMessage());
    }
  }
}
