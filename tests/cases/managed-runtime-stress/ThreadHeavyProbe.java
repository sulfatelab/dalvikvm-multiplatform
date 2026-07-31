/**
 * Phase 4 A6: heavier multi-thread monitors + wait/notify + interrupt.
 */
public class ThreadHeavyProbe {
  static final Object lock = new Object();
  static final Object gate = new Object();
  static int counter = 0;
  static volatile boolean go = false;

  public static void main(String[] args) throws Exception {
    final int n = 24;
    final int iters = 3000;
    Thread[] ts = new Thread[n];
    for (int i = 0; i < n; i++) {
      final int id = i;
      ts[i] = new Thread(() -> {
        synchronized (gate) {
          while (!go) {
            try { gate.wait(1000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
          }
        }
        for (int j = 0; j < iters; j++) {
          synchronized (lock) {
            counter++;
            if ((j & 255) == 0) {
              lock.notifyAll();
              try { lock.wait(0, 1); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
            }
          }
        }
      }, "heavy-" + id);
      ts[i].start();
    }
    Thread.sleep(50);
    synchronized (gate) { go = true; gate.notifyAll(); }
    for (Thread t : ts) t.join(60000);
    // interrupt a sleeper
    Thread sleeper = new Thread(() -> {
      try { Thread.sleep(60000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }, "sleeper");
    sleeper.start();
    sleeper.interrupt();
    sleeper.join(5000);
    boolean ok = counter == n * iters && !sleeper.isAlive();
    System.out.println("threads=" + n + " iters=" + iters + " counter=" + counter);
    System.out.println("interrupt.ok=" + !sleeper.isAlive());
    System.out.println("threadheavy.ok=" + ok);
    System.out.println("ThreadHeavyProbe.done=ok");
    if (!ok) System.exit(1);
  }
}
