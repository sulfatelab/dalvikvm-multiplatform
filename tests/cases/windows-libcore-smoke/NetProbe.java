import java.io.*;
import java.net.*;

/** Classic ServerSocket/Socket loopback probe (A7-oriented; not NIO.2). */
public class NetProbe {
  public static void main(String[] args) throws Exception {
    final String payload = "phase3-net-ok";
    final ServerSocket server = new ServerSocket();
    server.setReuseAddress(true);
    server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 1);
    server.setSoTimeout(10000);
    final int port = server.getLocalPort();
    System.out.println("server.port=" + port);
    System.out.flush();

    final String[] clientResp = new String[1];
    final Throwable[] clientErr = new Throwable[1];
    Thread client = new Thread(() -> {
      try {
        System.out.println("client.connecting");
        System.out.flush();
        Socket s = new Socket();
        s.connect(new InetSocketAddress("127.0.0.1", port), 5000);
        s.setSoTimeout(10000);
        System.out.println("client.connected local=" + s.getLocalSocketAddress()
            + " remote=" + s.getRemoteSocketAddress());
        System.out.flush();
        OutputStream out = s.getOutputStream();
        byte[] pb = payload.getBytes("UTF-8");
        out.write(pb);
        out.flush();
        System.out.println("client.wrote n=" + pb.length);
        System.out.flush();
        InputStream in = s.getInputStream();
        byte[] buf = new byte[64];
        int n = in.read(buf);
        clientResp[0] = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
        System.out.println("client.resp=" + clientResp[0] + " n=" + n);
        System.out.flush();
        s.close();
      } catch (Throwable t) {
        clientErr[0] = t;
        System.out.println("client.err=" + t);
        t.printStackTrace(System.out);
        System.out.flush();
      }
    }, "net-client");
    client.setDaemon(true);
    client.start();

    System.out.println("server.accepting");
    System.out.flush();
    Socket peer = server.accept();
    peer.setSoTimeout(10000);
    System.out.println("accepted=" + peer.getRemoteSocketAddress());
    System.out.flush();
    byte[] buf = new byte[64];
    int n = peer.getInputStream().read(buf);
    String got = n > 0 ? new String(buf, 0, n, "UTF-8") : "";
    System.out.println("server.got=" + got + " n=" + n);
    System.out.flush();
    byte[] echo = ("echo:" + got).getBytes("UTF-8");
    peer.getOutputStream().write(echo);
    peer.getOutputStream().flush();
    System.out.println("server.wroteEcho n=" + echo.length);
    System.out.flush();
    peer.close();
    server.close();
    client.join(15000);
    if (clientErr[0] != null) {
      System.out.println("client.finalErr=" + clientErr[0]);
    }
    System.out.println("match=" + payload.equals(got));
    System.out.println("echoMatch=" + ("echo:" + payload).equals(clientResp[0]));
    System.out.println("NetProbe.done=ok");
  }
}
