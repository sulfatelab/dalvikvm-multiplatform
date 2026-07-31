import java.io.*;
import java.net.*;

/**
 * Phase 4 resource/handle stress: many short-lived files and sockets.
 * Passes if no crash and final I/O still works.
 */
public class HandleLeakProbe {
  public static void main(String[] args) throws Exception {
    File dir = new File("run/tmp_handles");
    dir.mkdirs();
    int nFiles = 400;
    int nSocks = 80;
    for (int i = 0; i < nFiles; i++) {
      File f = new File(dir, "f" + i + ".txt");
      try (FileOutputStream out = new FileOutputStream(f)) {
        out.write(("x" + i).getBytes("UTF-8"));
      }
      try (FileInputStream in = new FileInputStream(f)) {
        if (in.read() < 0) throw new IOException("empty");
      }
      if (!f.delete()) {
        // retry once
        f.delete();
      }
    }
    System.out.println("files.ok=true n=" + nFiles);

    ServerSocket server = new ServerSocket();
    server.setReuseAddress(true);
    server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 32);
    server.setSoTimeout(10000);
    int port = server.getLocalPort();
    for (int i = 0; i < nSocks; i++) {
      Socket c = new Socket();
      c.connect(new InetSocketAddress("127.0.0.1", port), 3000);
      Socket p = server.accept();
      p.setSoTimeout(3000);
      c.setSoTimeout(3000);
      c.getOutputStream().write(7);
      int b = p.getInputStream().read();
      if (b != 7) throw new IOException("bad byte " + b);
      c.close();
      p.close();
    }
    server.close();
    System.out.println("socks.ok=true n=" + nSocks);

    // final sanity file
    File fin = new File(dir, "final.txt");
    try (FileOutputStream out = new FileOutputStream(fin)) { out.write("handle-final".getBytes("UTF-8")); }
    byte[] buf = new byte[32];
    int n;
    try (FileInputStream in = new FileInputStream(fin)) { n = in.read(buf); }
    String got = new String(buf, 0, Math.max(n,0), "UTF-8");
    boolean ok = "handle-final".equals(got);
    System.out.println("final=" + got);
    System.out.println("handleleak.ok=" + ok);
    System.out.println("HandleLeakProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
