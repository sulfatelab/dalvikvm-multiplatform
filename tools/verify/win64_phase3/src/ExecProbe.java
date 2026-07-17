import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.Charset;

/** L-003 smoke: Runtime.exec / ProcessBuilder under Win64 ART. */
public class ExecProbe {
  private static String readAll(Process p) throws Exception {
    StringBuilder sb = new StringBuilder();
    try (BufferedReader br = new BufferedReader(
            new InputStreamReader(p.getInputStream(), Charset.forName("UTF-8")))) {
      String line;
      while ((line = br.readLine()) != null) {
        if (sb.length() > 0) sb.append('\n');
        sb.append(line);
      }
    }
    return sb.toString();
  }

  public static void main(String[] args) throws Exception {
    try {
      ProcessBuilder pb = new ProcessBuilder("cmd.exe", "/c", "echo exec.probe.ok");
      pb.redirectErrorStream(true);
      Process p = pb.start();
      String out = readAll(p);
      int code = p.waitFor();
      System.out.println("exec.out=" + out);
      System.out.println("exec.code=" + code);
      if (!out.contains("exec.probe.ok") || code != 0) {
        throw new RuntimeException("ProcessBuilder failed out=[" + out + "] code=" + code);
      }

      Process p2 = Runtime.getRuntime().exec(new String[] {"cmd.exe", "/c", "echo runtime.exec.ok"});
      String out2 = readAll(p2);
      int code2 = p2.waitFor();
      System.out.println("runtime.out=" + out2);
      System.out.println("runtime.code=" + code2);
      if (!out2.contains("runtime.exec.ok") || code2 != 0) {
        throw new RuntimeException("Runtime.exec failed out=[" + out2 + "] code=" + code2);
      }
      System.out.println("ExecProbe.done=ok");
    } catch (Throwable t) {
      System.out.println("ExecProbe.fail=" + t);
      t.printStackTrace(System.out);
      if (t.getCause() != null) {
        System.out.println("cause=" + t.getCause());
        t.getCause().printStackTrace(System.out);
      }
      System.exit(1);
    }
  }
}
