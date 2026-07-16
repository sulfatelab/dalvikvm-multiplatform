/** A8-lite: uncaught exception path prints and exits non-zero without silent hang. */
public class ThrowProbe {
  public static void main(String[] args) {
    System.out.println("ThrowProbe.start");
    System.out.flush();
    if (args.length > 0 && "npe".equals(args[0])) {
      String s = null;
      // deliberate NPE
      System.out.println(s.length());
    }
    throw new RuntimeException("phase3-throw-ok");
  }
}
