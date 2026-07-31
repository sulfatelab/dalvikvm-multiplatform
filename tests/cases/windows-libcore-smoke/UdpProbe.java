import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;

/** L-003 smoke: classic UDP IPv4. IPv6 bind is best-effort under wine. */
public class UdpProbe {
  public static void main(String[] args) throws Exception {
    byte[] payload = "udp.probe.ok".getBytes("UTF-8");
    DatagramSocket server = new DatagramSocket(new InetSocketAddress("127.0.0.1", 0));
    int port = server.getLocalPort();
    System.out.println("udp.server.port=" + port);
    DatagramSocket client = new DatagramSocket();
    try {
      client.send(new DatagramPacket(payload, payload.length, InetAddress.getByName("127.0.0.1"), port));
      System.out.println("udp.sent=true");
      byte[] buf = new byte[64];
      DatagramPacket in = new DatagramPacket(buf, buf.length);
      server.setSoTimeout(2000);
      try {
        server.receive(in);
      } catch (SocketTimeoutException e) {
        throw new RuntimeException("udp receive timeout", e);
      }
      String got = new String(in.getData(), 0, in.getLength(), "UTF-8");
      System.out.println("udp.got=" + got);
      System.out.println("udp.from=" + in.getAddress() + ":" + in.getPort());
      if (!"udp.probe.ok".equals(got)) throw new RuntimeException("udp mismatch " + got);
    } finally {
      client.close();
      server.close();
    }
    System.out.println("udp6.note=skipped_under_wine_gate");
    System.out.println("UdpProbe.done=ok");
  }
}
