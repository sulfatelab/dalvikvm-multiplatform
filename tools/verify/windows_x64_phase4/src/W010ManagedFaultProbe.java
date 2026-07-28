public class W010ManagedFaultProbe {
  private static final int NPE_ROUNDS = 64;
  private static final int SO_ROUNDS = 2;

  private static volatile int sink;
  private static volatile int recoveryChecks;
  private static volatile int gcChecks;

  private static final class Cell {
    int value;
  }

  private static int readCell(Cell cell) {
    return cell.value;
  }

  private static void writeCell(Cell cell, int value) {
    cell.value = value;
  }

  private static int recurse(int remaining) {
    if (remaining == 0) {
      return 1;
    }
    return recurse(remaining - 1) + 1;
  }

  private static void warmup() {
    Cell cell = new Cell();
    for (int i = 0; i < 4096; ++i) {
      writeCell(cell, i);
      sink = readCell(cell);
      sink = recurse(8);
    }
  }

  private static void verifyRecovery(Throwable fault, boolean requestGc) {
    StackTraceElement[] trace = fault.getStackTrace();
    if (trace.length == 0) {
      throw new AssertionError("managed fault has no stack trace");
    }
    sink ^= trace[0].getLineNumber();
    sink ^= (int) System.nanoTime();
    sink ^= System.identityHashCode(new Object());
    ++recoveryChecks;
    if (requestGc) {
      System.gc();
      ++gcChecks;
    }
  }

  private static void runNullChecks() {
    int recoveryBefore = recoveryChecks;
    int gcBefore = gcChecks;
    int readCaught = 0;
    int writeCaught = 0;
    for (int i = 0; i < NPE_ROUNDS; ++i) {
      try {
        sink = readCell(null);
      } catch (NullPointerException expected) {
        ++readCaught;
        verifyRecovery(expected, (i & 7) == 0);
      }
      try {
        writeCell(null, i);
      } catch (NullPointerException expected) {
        ++writeCaught;
        verifyRecovery(expected, (i & 7) == 0);
      }
    }
    int recoveryDelta = recoveryChecks - recoveryBefore;
    int gcDelta = gcChecks - gcBefore;
    if (readCaught != NPE_ROUNDS || writeCaught != NPE_ROUNDS ||
        recoveryDelta != 2 * NPE_ROUNDS || gcDelta != NPE_ROUNDS / 4) {
      throw new AssertionError(
          "NPE counts read=" + readCaught + " write=" + writeCaught +
          " recovery=" + recoveryDelta + " gc=" + gcDelta);
    }
    System.out.println(
        "W010ManagedFaultProbe NPE OK read=" + readCaught + " write=" + writeCaught +
        " recovery=" + recoveryDelta + " gc=" + gcDelta);
  }

  private static int runStackOverflowRounds() {
    int caught = 0;
    for (int i = 0; i < SO_ROUNDS; ++i) {
      try {
        sink = recurse(Integer.MAX_VALUE);
      } catch (StackOverflowError expected) {
        ++caught;
        verifyRecovery(expected, true);
      }
    }
    return caught;
  }

  private static void runStackChecks() throws InterruptedException {
    int recoveryBefore = recoveryChecks;
    int gcBefore = gcChecks;
    int mainCaught = runStackOverflowRounds();
    final int[] childCaught = new int[1];
    Thread child = new Thread(
        () -> childCaught[0] = runStackOverflowRounds(),
        "w010-stack-child");
    child.start();
    child.join();
    int recoveryDelta = recoveryChecks - recoveryBefore;
    int gcDelta = gcChecks - gcBefore;
    if (mainCaught != SO_ROUNDS || childCaught[0] != SO_ROUNDS ||
        recoveryDelta != 2 * SO_ROUNDS || gcDelta != 2 * SO_ROUNDS) {
      throw new AssertionError(
          "SO counts main=" + mainCaught + " child=" + childCaught[0] +
          " recovery=" + recoveryDelta + " gc=" + gcDelta);
    }
    System.out.println(
        "W010ManagedFaultProbe SO OK main=" + mainCaught + " child=" + childCaught[0] +
        " recovery=" + recoveryDelta + " gc=" + gcDelta);
  }

  public static void main(String[] args) throws Exception {
    if (args.length != 1 ||
        !("npe".equals(args[0]) || "so".equals(args[0]) || "all".equals(args[0]))) {
      throw new IllegalArgumentException("expected mode: npe, so, or all");
    }

    warmup();
    if (!"so".equals(args[0])) {
      runNullChecks();
    }
    if (!"npe".equals(args[0])) {
      runStackChecks();
    }
    System.out.println("W010ManagedFaultProbe OK mode=" + args[0]);
  }
}
