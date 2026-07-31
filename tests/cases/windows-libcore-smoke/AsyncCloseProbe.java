import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;

/**
 * L-001: classic socket async-close — peer close unblocks accept/read.
 * Exercises libcore.io.AsynchronousCloseMonitor.signalBlockedThreads + Winsock shutdown.
 */
public class AsyncCloseProbe {
  public static void main(String[] args) throws Exception {
    final ServerSocket server = new ServerSocket();
    server.setReuseAddress(true);
    server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 1);
    final int port = server.getLocalPort();
    System.out.println("server.port=" + port);
    System.out.flush();

    final Throwable[] acceptErr = new Throwable[1];
    final boolean[] acceptReturned = {false};
    Thread acceptor = new Thread(() -> {
      try {
        System.out.println("accept.blocking");
        System.out.flush();
        Socket peer = server.accept();
        acceptReturned[0] = true;
        System.out.println("accept.unexpectedPeer=" + peer);
        peer.close();
      } catch (Throwable t) {
        acceptErr[0] = t;
        acceptReturned[0] = true;
        System.out.println("accept.err=" + t.getClass().getName() + ": " + t.getMessage());
        System.out.flush();
      }
    }, "async-accept");
    acceptor.setDaemon(true);
    acceptor.start();

    // Give acceptor time to enter accept
    Thread.sleep(300);
    System.out.println("server.closing");
    System.out.flush();
    server.close();
    acceptor.join(5000);
    boolean acceptOk = acceptReturned[0] && !acceptor.isAlive()
        && acceptErr[0] instanceof SocketException;
    System.out.println("accept.unblocked=" + acceptOk
        + " alive=" + acceptor.isAlive()
        + " errClass=" + (acceptErr[0] == null ? "null" : acceptErr[0].getClass().getName()));
    System.out.flush();

    // Read path: client connects, server accepts, client blocks on read, server closes peer
    final ServerSocket s2 = new ServerSocket();
    s2.setReuseAddress(true);
    s2.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 1);
    final int p2 = s2.getLocalPort();
    final Throwable[] readErr = new Throwable[1];
    final boolean[] readReturned = {false};
    Thread client = new Thread(() -> {
      try {
        Socket c = new Socket();
        c.connect(new InetSocketAddress("127.0.0.1", p2), 3000);
        c.setSoTimeout(0); // infinite
        System.out.println("client.reading");
        System.out.flush();
        InputStream in = c.getInputStream();
        int n = in.read(); // block until close/shutdown
        readReturned[0] = true;
        System.out.println("client.read.n=" + n);
        c.close();
      } catch (Throwable t) {
        readErr[0] = t;
        readReturned[0] = true;
        System.out.println("client.read.err=" + t.getClass().getName() + ": " + t.getMessage());
        System.out.flush();
      }
    }, "async-read");
    client.setDaemon(true);
    client.start();
    Socket peer = s2.accept();
    Thread.sleep(200);
    System.out.println("peer.closing");
    System.out.flush();
    peer.close();
    s2.close();
    client.join(5000);
    // EOF (n==-1) or SocketException both acceptable after async close/shutdown
    boolean readOk = readReturned[0] && !client.isAlive()
        && (readErr[0] == null || readErr[0] instanceof SocketException
            || readErr[0] instanceof java.io.IOException);
    System.out.println("read.unblocked=" + readOk
        + " alive=" + client.isAlive()
        + " errClass=" + (readErr[0] == null ? "null" : readErr[0].getClass().getName()));
    System.out.flush();

    boolean ok = acceptOk && readOk;
    System.out.println("AsyncCloseProbe.done=" + (ok ? "ok" : "fail"));
    System.out.flush();
    if (!ok) System.exit(1);
  }
}
