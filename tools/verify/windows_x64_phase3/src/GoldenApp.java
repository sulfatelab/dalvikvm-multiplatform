import java.io.*;
import java.net.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Phase 3 product-class golden app (A4–A7 combined):
 * - write/read config via classic java.io (mixed separators)
 * - multi-thread workers with monitors
 * - loopback TCP server + concurrent clients
 * - light allocation churn
 *
 * NIO.2 intentionally unused.
 */
public class GoldenApp {
  static final String PAYLOAD_PREFIX = "golden-";

  public static void main(String[] args) throws Exception {
    File confDir = new File("run/tmp_golden/conf");
    confDir.mkdirs();
    // mixed path
    File conf = new File("run/tmp_golden/conf\\app.cfg".replace('\\', File.separatorChar));
    // Force mixed construction as product may do
    conf = new File("run/tmp_golden/conf/app.cfg");
    String confBody = "mode=server\nport=0\nname=phase3\n";
    try (FileOutputStream out = new FileOutputStream(conf)) {
      out.write(confBody.getBytes("UTF-8"));
    }
    String confRead;
    try (FileInputStream in = new FileInputStream(conf)) {
      byte[] buf = new byte[256];
      int n = in.read(buf);
      confRead = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
    }
    System.out.println("conf.match=" + confBody.equals(confRead));
    System.out.println("conf.path=" + conf.getPath());
    System.out.println("conf.abs=" + conf.getAbsolutePath());

    ServerSocket server = new ServerSocket();
    server.setReuseAddress(true);
    server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 16);
    // Prevent infinite accept poll(-1) if clients fail to connect (real Win10 localhost dual-stack pitfalls).
    server.setSoTimeout(15000);
    final int port = server.getLocalPort();
    System.out.println("server.port=" + port);

    final int clients = 4;
    final int msgsPerClient = 8;
    final AtomicInteger served = new AtomicInteger();
    final AtomicInteger okEcho = new AtomicInteger();
    CountDownLatch serverReady = new CountDownLatch(1);
    CountDownLatch clientsDone = new CountDownLatch(clients);

    Thread acceptor = new Thread(() -> {
      try {
        serverReady.countDown();
        int remaining = clients * msgsPerClient;
        // Each client opens one connection and sends msgsPerClient messages? Use one conn per client.
        for (int c = 0; c < clients; c++) {
          Socket peer = server.accept();
          peer.setSoTimeout(10000);
          try {
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            byte[] buf = new byte[256];
            for (int m = 0; m < msgsPerClient; m++) {
              int n = readLineish(in, buf);
              if (n <= 0) break;
              String got = new String(buf, 0, n, "UTF-8");
              served.incrementAndGet();
              byte[] resp = ("OK:" + got).getBytes("UTF-8");
              out.write(resp);
              out.write('\n');
              out.flush();
            }
          } finally {
            peer.close();
          }
        }
      } catch (Throwable t) {
        System.out.println("server.err=" + t);
        t.printStackTrace(System.out);
      }
    }, "golden-acceptor");
    acceptor.start();
    serverReady.await();

    List<Thread> workers = new ArrayList<>();
    for (int i = 0; i < clients; i++) {
      final int id = i;
      Thread t = new Thread(() -> {
        try {
          // light allocation churn per worker
          List<byte[]> junk = new ArrayList<>();
          for (int k = 0; k < 50; k++) junk.add(new byte[4096]);

          Socket s = new Socket();
          s.connect(new InetSocketAddress("127.0.0.1", port), 5000);
          s.setSoTimeout(10000);
          InputStream in = s.getInputStream();
          OutputStream out = s.getOutputStream();
          byte[] buf = new byte[256];
          for (int m = 0; m < msgsPerClient; m++) {
            String msg = PAYLOAD_PREFIX + id + "-" + m;
            out.write(msg.getBytes("UTF-8"));
            out.write('\n');
            out.flush();
            int n = readLineish(in, buf);
            String resp = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
            if (("OK:" + msg).equals(resp)) okEcho.incrementAndGet();
          }
          s.close();
          junk.clear();
        } catch (Throwable ex) {
          System.out.println("client" + id + ".err=" + ex);
          ex.printStackTrace(System.out);
        } finally {
          clientsDone.countDown();
        }
      }, "golden-client-" + i);
      workers.add(t);
      t.start();
    }

    clientsDone.await();
    acceptor.join(15000);
    server.close();

    int expected = clients * msgsPerClient;
    System.out.println("served=" + served.get() + " okEcho=" + okEcho.get() + " expected=" + expected);
    boolean netOk = served.get() == expected && okEcho.get() == expected;
    System.out.println("net.ok=" + netOk);

    // interrupt sanity in golden context
    Thread sleeper = new Thread(() -> {
      try { Thread.sleep(30000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    });
    sleeper.start();
    sleeper.interrupt();
    sleeper.join(3000);
    System.out.println("interrupt.ok=" + !sleeper.isAlive());

    System.gc();
    boolean all = confBody.equals(confRead) && netOk && !sleeper.isAlive();
    System.out.println("golden.ok=" + all);
    System.out.println("GoldenApp.done=ok");
    if (!all) System.exit(1);
  }

  /** Read until '\\n' or buffer full; returns bytes excluding newline. */
  static int readLineish(InputStream in, byte[] buf) throws IOException {
    int n = 0;
    while (n < buf.length) {
      int b = in.read();
      if (b < 0) return n == 0 ? -1 : n;
      if (b == '\n') return n;
      buf[n++] = (byte) b;
    }
    return n;
  }
}
