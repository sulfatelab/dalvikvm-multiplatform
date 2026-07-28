import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/** Exercises the product non-moving allocator with sub-LOS primitive arrays. */
public final class W013NonMovingStressProbe {
  private static final int ARRAY_BYTES = 8 * 1024;
  private static final int ARRAYS_PER_ROUND = 768;
  private static final int ROUNDS = 12;
  private static final int MAX_LIVE = 1024;
  private static final long FOUR_GB = 1L << 32;

  private static long sink;

  public static void main(String[] args) throws Exception {
    Class<?> vmRuntimeClass = Class.forName("dalvik.system.VMRuntime");
    Method getRuntime = vmRuntimeClass.getDeclaredMethod("getRuntime");
    Method newNonMovableArray =
        vmRuntimeClass.getDeclaredMethod("newNonMovableArray", Class.class, int.class);
    Method addressOf = vmRuntimeClass.getDeclaredMethod("addressOf", Object.class);
    getRuntime.setAccessible(true);
    newNonMovableArray.setAccessible(true);
    addressOf.setAccessible(true);
    Object vmRuntime = getRuntime.invoke(null);

    List<byte[]> live = new ArrayList<>();
    List<byte[]> anchors = new ArrayList<>();
    List<Long> anchorAddresses = new ArrayList<>();
    long minAddress = Long.MAX_VALUE;
    long maxAddress = 0;
    long totalBytes = 0;

    for (int round = 0; round < ROUNDS; ++round) {
      for (int i = 0; i < ARRAYS_PER_ROUND; ++i) {
        byte[] array = (byte[]) newNonMovableArray.invoke(vmRuntime, byte.class, ARRAY_BYTES);
        array[0] = (byte) (round + i);
        array[array.length - 1] = (byte) (round ^ i);
        sink += (array[0] & 0xff) + (array[array.length - 1] & 0xff);
        totalBytes += array.length;

        if ((i & 31) == 0) {
          long address = (Long) addressOf.invoke(vmRuntime, array);
          if (address <= 0 || address >= FOUR_GB) {
            throw new AssertionError("non-moving array address out of low heap: 0x"
                + Long.toHexString(address));
          }
          minAddress = Math.min(minAddress, address);
          maxAddress = Math.max(maxAddress, address);
        }

        if (anchors.size() < 16 && (i & 63) == 0) {
          anchors.add(array);
          anchorAddresses.add((Long) addressOf.invoke(vmRuntime, array));
        }
        if ((i & 1) == 0) {
          live.add(array);
          if (live.size() > MAX_LIVE) {
            live.remove(0);
          }
        }
      }

      System.gc();
      for (int i = 0; i < anchors.size(); ++i) {
        long current = (Long) addressOf.invoke(vmRuntime, anchors.get(i));
        if (current != anchorAddresses.get(i)) {
          throw new AssertionError("non-moving array moved across GC");
        }
      }
      System.out.println("round=" + round
          + " live=" + live.size()
          + " total_bytes=" + totalBytes
          + " span=" + (maxAddress - minAddress));
    }

    live.clear();
    System.gc();
    for (int i = 0; i < ARRAYS_PER_ROUND; ++i) {
      byte[] array = (byte[]) newNonMovableArray.invoke(vmRuntime, byte.class, ARRAY_BYTES);
      array[0] = (byte) i;
      sink += array[0] & 0xff;
      if ((i & 3) == 0) {
        live.add(array);
      }
    }

    long span = maxAddress - minAddress;
    boolean ok = totalBytes >= 64L * 1024L * 1024L
        && span > 2L * 1024L * 1024L
        && anchors.size() == 16
        && !live.isEmpty()
        && sink != 0;
    System.out.println("nonmoving.total_bytes=" + totalBytes);
    System.out.println("nonmoving.address_span=" + span);
    System.out.println("nonmoving.stable=true");
    System.out.println("nonmoving.low=true");
    System.out.println("nonmoving.ok=" + ok);
    System.out.println("W013NonMovingStressProbe.done=ok");
    if (!ok) {
      System.exit(1);
    }
  }
}
