public class FS1StackHighWaterProbe {
  private static final int ROUNDS = 2;
  private static volatile int sink;

  static {
    System.loadLibrary("fs1stackhighwater");
  }

  private static native boolean dumpHighWater(String label);

  private static int recurse(int remaining) {
    if (remaining == 0) {
      return 1;
    }
    return recurse(remaining - 1) + 1;
  }

  private static void warmup() {
    for (int i = 0; i < 4096; ++i) {
      sink = recurse(8);
    }
  }

  private static int runRounds(String threadLabel) {
    int caught = 0;
    for (int round = 1; round <= ROUNDS; ++round) {
      try {
        sink = recurse(Integer.MAX_VALUE);
      } catch (StackOverflowError expected) {
        StackTraceElement[] trace = expected.getStackTrace();
        if (trace.length == 0) {
          throw new AssertionError("stack overflow has no managed trace");
        }
        sink ^= trace[0].getLineNumber();
        sink ^= System.identityHashCode(new Object());
        String label = threadLabel + "-" + round;
        if (!dumpHighWater(label)) {
          throw new AssertionError("incomplete native high-water record: " + label);
        }
        ++caught;
      }
    }
    return caught;
  }

  public static void main(String[] args) throws Exception {
    if (args.length != 1) {
      throw new IllegalArgumentException("expected execution-mode label");
    }
    warmup();
    int mainCaught = runRounds("main");
    final int[] childCaught = new int[1];
    final Throwable[] childFailure = new Throwable[1];
    Thread child = new Thread(() -> {
      try {
        childCaught[0] = runRounds("child");
      } catch (Throwable failure) {
        childFailure[0] = failure;
      }
    }, "fs1-stack-child");
    child.start();
    child.join();
    if (childFailure[0] != null) {
      throw new AssertionError("child probe failed", childFailure[0]);
    }
    if (mainCaught != ROUNDS || childCaught[0] != ROUNDS) {
      throw new AssertionError(
          "wrong catch counts main=" + mainCaught + " child=" + childCaught[0]);
    }
    System.out.println(
        "FS1StackHighWaterProbe OK mode=" + args[0] +
        " main=" + mainCaught + " child=" + childCaught[0]);
  }
}
