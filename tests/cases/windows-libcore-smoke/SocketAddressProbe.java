import android.system.Os;
import android.system.OsConstants;
import java.io.FileDescriptor;
import java.net.InetAddress;
import java.net.InetSocketAddress;

/** W-007: Os.bind/connect SocketAddress overloads (InetSocketAddress). */
public class SocketAddressProbe {
  public static void main(String[] args) throws Exception {
    FileDescriptor fd = Os.socket(OsConstants.AF_INET, OsConstants.SOCK_STREAM, 0);
    Os.bind(fd, new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0));
    Os.listen(fd, 1);
    InetSocketAddress local = (InetSocketAddress) Os.getsockname(fd);
    System.out.println("bound.port=" + local.getPort());
    FileDescriptor cfd = Os.socket(OsConstants.AF_INET, OsConstants.SOCK_STREAM, 0);
    Os.connect(cfd, new InetSocketAddress(InetAddress.getByName("127.0.0.1"), local.getPort()));
    FileDescriptor afd = Os.accept(fd, null);
    System.out.println("accepted=true peer=" + Os.getpeername(afd));
    Os.close(cfd);
    Os.close(afd);
    Os.close(fd);
    System.out.println("SocketAddressProbe.done=ok");
  }
}
