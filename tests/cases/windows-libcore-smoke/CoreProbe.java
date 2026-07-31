/** A4-oriented core libcore probe: concurrency, charset, arraycopy, reflection. */
public class CoreProbe {
  static final Object lock = new Object();
  static int counter = 0;

  public static void main(String[] args) throws Exception {
    // arraycopy
    int[] a = {1,2,3,4};
    int[] b = new int[4];
    System.arraycopy(a, 0, b, 0, 4);
    System.out.println("arraycopy=" + (b[0]==1 && b[3]==4));

    // charset
    byte[] utf = "hello-χ".getBytes("UTF-8");
    String back = new String(utf, "UTF-8");
    System.out.println("charset=" + back.equals("hello-χ") + " nbytes=" + utf.length);

    // reflection
    Class<?> c = Class.forName("java.lang.String");
    Object s = c.getConstructor(String.class).newInstance("reflect-ok");
    System.out.println("reflect=" + s);

    // threads + monitor
    Thread t1 = new Thread(() -> {
      for (int i = 0; i < 1000; i++) {
        synchronized (lock) { counter++; }
      }
    });
    Thread t2 = new Thread(() -> {
      for (int i = 0; i < 1000; i++) {
        synchronized (lock) { counter++; }
      }
    });
    t1.start(); t2.start();
    t1.join(); t2.join();
    System.out.println("threads.counter=" + counter);
    System.out.println("threads.ok=" + (counter == 2000));
    System.out.println("CoreProbe.done=ok");
  }
}
