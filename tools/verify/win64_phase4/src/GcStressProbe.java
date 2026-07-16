import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Phase 4 A5: stronger GC stress — tiny + LOS churn with interleaved System.gc().
 */
public class GcStressProbe {
  static volatile long sink;
  public static void main(String[] args) throws Exception {
    Runtime rt = Runtime.getRuntime();
    Random rnd = new Random(99);
    List<Object> live = new ArrayList<>();
    long t0 = System.nanoTime();
    for (int round = 0; round < 8; round++) {
      for (int i = 0; i < 4000; i++) {
        byte[] a = new byte[32 + (i % 256)];
        a[0] = (byte) rnd.nextInt();
        sink += a[0] & 0xff;
        if ((i & 15) == 0) {
          live.add(a);
          if (live.size() > 300) live.remove(0);
        }
      }
      for (int i = 0; i < 80; i++) {
        byte[] a = new byte[24 * 1024];
        a[0] = (byte) rnd.nextInt();
        a[a.length - 1] = (byte) i;
        sink += (a[0] & 0xff) + (a[a.length - 1] & 0xff);
        if ((i & 3) == 0) {
          live.add(a);
          if (live.size() > 360) live.remove(0);
        }
      }
      System.gc();
      System.out.println("round=" + round + " free=" + rt.freeMemory() + " live=" + live.size() + " sink=" + sink);
      System.out.flush();
    }
    long checksum = 0;
    for (Object o : live) checksum += (((byte[]) o)[0] & 0xff);
    long ms = (System.nanoTime() - t0) / 1_000_000L;
    boolean ok = live.size() > 0 && sink != 0 && checksum >= 0;
    System.out.println("checksum=" + checksum + " ms=" + ms);
    System.out.println("gcstress.ok=" + ok);
    System.out.println("GcStressProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
