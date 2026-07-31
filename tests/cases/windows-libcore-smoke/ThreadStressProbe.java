/** A6 stress: many threads contending monitors + join. */
public class ThreadStressProbe {
  static final Object lock = new Object();
  static int counter = 0;
  public static void main(String[] args) throws Exception {
    int n = 16;
    int iters = 2000;
    Thread[] ts = new Thread[n];
    for (int i = 0; i < n; i++) {
      ts[i] = new Thread(() -> {
        for (int j = 0; j < iters; j++) {
          synchronized (lock) { counter++; }
        }
      }, "stress-" + i);
      ts[i].start();
    }
    for (Thread t : ts) t.join(30000);
    boolean ok = counter == n * iters;
    System.out.println("threads=" + n + " iters=" + iters + " counter=" + counter);
    System.out.println("threadstress.ok=" + ok);
    System.out.println("ThreadStressProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
