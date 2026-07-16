/**
 * Phase 4 light performance smoke (not a benchmark gate): arraycopy + string work complete quickly.
 */
public class PerfSmokeProbe {
  static volatile long sink;
  public static void main(String[] args) {
    long t0 = System.nanoTime();
    int[] a = new int[1 << 16];
    int[] b = new int[a.length];
    for (int i = 0; i < a.length; i++) a[i] = i;
    for (int r = 0; r < 200; r++) {
      System.arraycopy(a, 0, b, 0, a.length);
      sink += b[r & 255];
      String s = "perf-" + r + "-" + (r * 17);
      sink += s.hashCode();
    }
    long ms = (System.nanoTime() - t0) / 1_000_000L;
    boolean ok = sink != 0 && ms < 60000;
    System.out.println("ms=" + ms + " sink=" + sink);
    System.out.println("perf.ok=" + ok);
    System.out.println("PerfSmokeProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
