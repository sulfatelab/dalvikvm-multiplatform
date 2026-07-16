/** A6 interruption smoke: exact GoldenApp sleeper pattern. */
public class InterruptProbe {
  public static void main(String[] args) throws Exception {
    System.out.println("InterruptProbe.start");
    System.out.flush();
    Thread sleeper = new Thread(() -> {
      try { Thread.sleep(30000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    });
    sleeper.start();
    System.out.println("InterruptProbe.started");
    System.out.flush();
    sleeper.interrupt();
    System.out.println("InterruptProbe.interrupted");
    System.out.flush();
    sleeper.join(3000);
    System.out.println("alive=" + sleeper.isAlive());
    System.out.flush();
    boolean ok = !sleeper.isAlive();
    System.out.println("interrupt.ok=" + ok);
    System.out.println("InterruptProbe.done=ok");
    System.out.flush();
    if (!ok) System.exit(1);
  }
}
