import android.system.Os;
import android.system.OsConstants;
import java.io.FileDescriptor;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;

/** W-007: Os.bind/connect SocketAddress overloads (InetSocketAddress). */
public class SocketAddressProbe {
  public static void main(String[] args) throws Exception {
    FileDescriptor fd = Os.socket(OsConstants.AF_INET, OsConstants.SOCK_STREAM, 0);
    Os.bind(fd, new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0));
    Os.listen(fd, 1);
    InetSocketAddress local = (InetSocketAddress) Os.getsockname(fd);
    if (local.getPort() <= 0 || !local.getAddress().isLoopbackAddress()) {
      throw new AssertionError("invalid bound address: " + local);
    }
    System.out.println("bound.port=" + local.getPort());
    System.out.println("bound.loopback=true");
    FileDescriptor cfd = Os.socket(OsConstants.AF_INET, OsConstants.SOCK_STREAM, 0);
    Os.connect(cfd, new InetSocketAddress(InetAddress.getByName("127.0.0.1"), local.getPort()));
    FileDescriptor afd = Os.accept(fd, null);
    SocketAddress peer = Os.getpeername(afd);
    if (!(peer instanceof InetSocketAddress)
        || ((InetSocketAddress) peer).getPort() <= 0
        || !((InetSocketAddress) peer).getAddress().isLoopbackAddress()) {
      throw new AssertionError("invalid accepted peer: " + peer);
    }
    System.out.println("accepted=true peer=" + peer);
    System.out.println("peer.loopback=true");
    Os.close(cfd);
    Os.close(afd);
    Os.close(fd);
    System.out.println("SocketAddressProbe.done=ok");
  }
}
