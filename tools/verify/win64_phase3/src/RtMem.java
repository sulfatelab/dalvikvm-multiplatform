import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
public class RtMem {
  public static void main(String[] args) throws Exception {
    Runtime r = Runtime.getRuntime();
    Method m = Runtime.class.getDeclaredMethod("freeMemory");
    System.out.println("freeMemory.mod=" + Modifier.toString(m.getModifiers()));
    System.out.println("native=" + Modifier.isNative(m.getModifiers()));
    try {
      long f=r.freeMemory(), t=r.totalMemory(), x=r.maxMemory();
      System.out.println("free="+f+" total="+t+" max="+x);
      System.out.println("mem.ok=" + (x > 0 && t >= 0 && f >= 0 && x >= t));
    } catch (Throwable e) {
      System.out.println("mem.err=" + e);
      e.printStackTrace(System.out);
    }
    System.out.println("RtMem.done=ok");
  }
}
