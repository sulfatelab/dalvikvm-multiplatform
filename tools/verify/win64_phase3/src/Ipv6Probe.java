import java.io.FileDescriptor;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import libcore.io.Libcore;
import android.system.OsConstants;

/** L-003 IPv6 dual-stack Os.socket bind; avoid IPv6 reverse-DNS (wine hang). */
public class Ipv6Probe {
  private static void say(String s) { System.out.println(s); System.out.flush(); }
  private static String hexAddr(InetAddress a) {
    byte[] b = a.getAddress();
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < b.length; i++) {
      if (i > 0) sb.append(':');
      sb.append(String.format("%02x", b[i] & 0xff));
    }
    return sb.toString();
  }
  public static void main(String[] args) throws Exception {
    say("Ipv6Probe.start=true");
    InetAddress any6 = InetAddress.getByAddress(new byte[16]);
    say("ipv6.any.hex=" + hexAddr(any6) + " is6=" + (any6 instanceof Inet6Address));
    if (!(any6 instanceof Inet6Address)) throw new RuntimeException("not v6");
    say("consts.af_inet6=" + OsConstants.AF_INET6 + " sock_dgram=" + OsConstants.SOCK_DGRAM);
    FileDescriptor fd = Libcore.os.socket(OsConstants.AF_INET6, OsConstants.SOCK_DGRAM, 0);
    say("ipv6.socket.fd=" + fd);
    try {
      Libcore.os.bind(fd, any6, 0);
      say("ipv6.bind.ok=true");
      Object sa = Libcore.os.getsockname(fd);
      say("ipv6.getsockname.class=" + (sa == null ? "null" : sa.getClass().getName()));
      if (sa instanceof InetSocketAddress) {
        InetSocketAddress isa = (InetSocketAddress) sa;
        InetAddress a = isa.getAddress();
        say("ipv6.getsockname.port=" + isa.getPort() + " addr.len=" + (a == null ? -1 : a.getAddress().length));
      }
    } finally {
      try { Libcore.os.close(fd); } catch (Throwable t) { say("close=" + t); }
    }
    say("ipv6.tcp.note=host_matrix_or_wine_partial");
    say("Ipv6Probe.done=ok");
  }
}
