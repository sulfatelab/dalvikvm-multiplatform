import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * A7 DNS/getaddrinfo smoke for Win64.
 *
 * Important on real Windows: getAllByName("localhost") often prefers IPv6 (::1).
 * A ServerSocket bound only to 127.0.0.1 will never see a ::1 connect, and without
 * SO_TIMEOUT accept/poll(-1) hangs forever. Connect the data path to 127.0.0.1;
 * keep name resolution as a separate assertion.
 */
public class DnsProbe {
  public static void main(String[] args) throws Exception {
    InetAddress[] locals = InetAddress.getAllByName("localhost");
    System.out.println("localhost.count=" + locals.length);
    boolean hasLoop = false;
    boolean hasV4 = false;
    boolean hasV6 = false;
    for (InetAddress a : locals) {
      System.out.println("localhost.addr=" + a.getHostAddress());
      if (a.isLoopbackAddress()) hasLoop = true;
      if (a instanceof java.net.Inet4Address) hasV4 = true;
      if (a instanceof java.net.Inet6Address) hasV6 = true;
    }
    System.out.println("localhost.loopback=" + hasLoop);
    System.out.println("localhost.v4=" + hasV4 + " v6=" + hasV6);

    InetAddress n = InetAddress.getByName("127.0.0.1");
    System.out.println("numeric=" + n.getHostAddress());

    final ServerSocket server = new ServerSocket();
    server.setReuseAddress(true);
    server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 1);
    // Must set SO_TIMEOUT: Socket timeout 0 means poll forever (PlainSocketImpl).
    server.setSoTimeout(10000);
    final int port = server.getLocalPort();
    System.out.println("server.port=" + port);
    System.out.flush();

    final String[] clientResp = new String[1];
    final Throwable[] clientErr = new Throwable[1];
    Thread t = new Thread(() -> {
      try {
        // Use IPv4 loopback explicitly — not "localhost" (may be ::1 on Win10).
        Socket s = new Socket();
        s.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 5000);
        s.setSoTimeout(10000);
        s.getOutputStream().write("dns-ok".getBytes("UTF-8"));
        s.getOutputStream().flush();
        s.close();
        clientResp[0] = "sent";
      } catch (Exception e) {
        clientErr[0] = e;
        System.out.println("client.err=" + e);
      }
    }, "dns-client");
    t.setDaemon(true);
    t.start();

    Socket peer = server.accept();
    peer.setSoTimeout(10000);
    byte[] buf = new byte[16];
    int nread = peer.getInputStream().read(buf);
    String got = nread > 0 ? new String(buf, 0, nread, "UTF-8") : "";
    peer.close();
    server.close();
    t.join(5000);
    if (clientErr[0] != null) {
      System.out.println("client.finalErr=" + clientErr[0]);
    }
    System.out.println("payload=" + got);
    boolean ok = hasLoop && "dns-ok".equals(got);
    System.out.println("dns.ok=" + ok);
    System.out.println("DnsProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
