import java.lang.reflect.Field;

/** Focused Win64 compiled-JNI/FastNative argument mapping probe. */
public final class FastNativeAbiProbe {
  public static final class Holder {
    public double value;
  }

  private static void check(boolean condition, String message) {
    if (!condition) {
      throw new AssertionError(message);
    }
  }

  public static void main(String[] args) throws Exception {
    Holder holder = new Holder();
    Field value = Holder.class.getField("value");

    for (int i = 0; i < 1000; ++i) {
      double expected = i * 0.5 + 0.25;
      value.setDouble(holder, expected);
      check(value.getDouble(holder) == expected, "Field double mismatch at " + i);
    }

    int[] source = new int[32];
    int[] destination = new int[32];
    for (int i = 0; i < source.length; ++i) {
      source[i] = 0x1000 + i;
    }
    for (int i = 0; i < 1000; ++i) {
      int sourceOffset = i & 7;
      int destinationOffset = 16 - sourceOffset;
      System.arraycopy(source, sourceOffset, destination, destinationOffset, 8);
      check(destination[destinationOffset] == source[sourceOffset],
          "arraycopy first mismatch at " + i);
      check(destination[destinationOffset + 7] == source[sourceOffset + 7],
          "arraycopy last mismatch at " + i);
    }

    System.out.println("FastNativeAbiProbe OK");
  }
}
