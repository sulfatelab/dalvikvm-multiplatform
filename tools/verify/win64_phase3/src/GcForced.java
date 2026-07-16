import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * A5 forced GC gate: tiny + LOS allocation then explicit System.gc().
 * Product-relevant because GoldenApp and many apps call System.gc().
 */
public class GcForced {
  static volatile long sink;

  public static void main(String[] args) throws Exception {
    Runtime rt = Runtime.getRuntime();
    System.out.println("mem0 free=" + rt.freeMemory() + " total=" + rt.totalMemory() + " max=" + rt.maxMemory());
    System.out.flush();

    Random rnd = new Random(42);
    List<Object> live = new ArrayList<>();

    // Tiny object churn
    for (int i = 0; i < 5000; i++) {
      byte[] a = new byte[64 + (i % 128)];
      a[0] = (byte) rnd.nextInt();
      sink += a[0] & 0xff;
      if ((i % 16) == 0) {
        live.add(a);
        if (live.size() > 200) live.remove(0);
      }
    }
    System.out.println("tiny.ok=true live=" + live.size() + " sink=" + sink);
    System.out.flush();

    // LOS multi-KB churn
    for (int i = 0; i < 200; i++) {
      byte[] a = new byte[16 * 1024];
      a[0] = (byte) rnd.nextInt();
      a[a.length - 1] = (byte) i;
      sink += (a[0] & 0xff) + (a[a.length - 1] & 0xff);
      if ((i % 4) == 0) {
        live.add(a);
        if (live.size() > 250) live.remove(0);
      }
    }
    System.out.println("los.ok=true live=" + live.size() + " sink=" + sink);
    System.out.flush();

    long before = rt.freeMemory();
    System.out.println("before.gc free=" + before);
    System.out.flush();

    System.gc();
    System.out.println("after.gc free=" + rt.freeMemory());
    System.out.flush();

    // Keep live set reachable and re-touch
    long checksum = 0;
    for (Object o : live) {
      byte[] a = (byte[]) o;
      checksum += a[0] & 0xff;
    }
    System.out.println("checksum=" + checksum + " live=" + live.size());
    boolean ok = live.size() > 0 && sink != 0;
    System.out.println("gc.forced.ok=" + ok);
    System.out.println("GcForced.done=ok");
    System.out.flush();
    if (!ok) System.exit(1);
  }
}
