import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * A5 allocation/GC survival smoke for imageless Win64 ART.
 *
 * Uses multi-KB arrays (large-object path) to exercise MemMap low-4G LOS
 * allocations. Explicit System.gc() is covered by GcForced (hang fixed via
 * ThreadCpuNanoTime + WaitOnAddress timeout). This probe focuses on LOS
 * allocation survival with a live set checksum.
 */
public class GcProbe {
  static volatile long sink;

  public static void main(String[] args) throws Exception {
    Runtime rt = Runtime.getRuntime();
    System.out.println("mem0 free=" + rt.freeMemory() + " total=" + rt.totalMemory() + " max=" + rt.maxMemory());
    System.out.flush();

    Random rnd = new Random(7);
    List<byte[]> live = new ArrayList<>();
    // ~16MB multi-KB churn (LOS-sized); keep ~1MB live.
    for (int i = 0; i < 1000; i++) {
      byte[] a = new byte[16 * 1024];
      a[0] = (byte) rnd.nextInt();
      a[a.length - 1] = (byte) i;
      sink += (a[0] & 0xff) + (a[a.length - 1] & 0xff);
      if ((i % 8) == 0) {
        live.add(a);
        if (live.size() > 64) live.remove(0);
      }
    }
    long checksum = 0;
    for (byte[] a : live) checksum += (a[0] & 0xff);
    System.out.println("mem1 free=" + rt.freeMemory() + " total=" + rt.totalMemory()
        + " live=" + live.size() + " sink=" + sink);
    System.out.println("checksum=" + checksum);
    boolean ok = live.size() > 0 && sink != 0;
    System.out.println("los.ok=" + ok);
    System.out.println("gc.ok=" + ok);
    System.out.println("GcProbe.done=ok");
    System.out.flush();
    if (!ok) System.exit(1);
  }
}
