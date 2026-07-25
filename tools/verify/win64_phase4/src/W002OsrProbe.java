public final class W002OsrProbe {
    private static final int COUNT = 300_000;
    private static final long EXPECTED = 9_835_131_152L;
    private static volatile Object sink;

    private static long osrLoop(int count) {
        Thread expectedThread = Thread.currentThread();
        Object[] retained = new Object[256];
        long checksum = 0;
        float floatValue = 3.5f;
        double doubleValue = 17.25d;

        for (int i = 0; i < count; ++i) {
            checksum += ((i * 17L) ^ (i >>> 3)) & 0xffffL;
            floatValue += 0.5f;
            floatValue -= 0.5f;
            doubleValue += 0.25d;
            doubleValue -= 0.25d;

            if ((i & 255) == 0) {
                if (Thread.currentThread() != expectedThread) {
                    throw new AssertionError("Thread.currentThread changed during OSR");
                }
                byte[] block = new byte[64 + (i & 31)];
                block[0] = (byte) i;
                retained[(i >>> 8) & 255] = block;
            }
        }

        if (floatValue != 3.5f || doubleValue != 17.25d) {
            throw new AssertionError(
                    "floating values changed: " + floatValue + ", " + doubleValue);
        }
        sink = retained;
        return checksum;
    }

    public static void main(String[] args) {
        long checksum = osrLoop(COUNT);
        if (checksum != EXPECTED || sink == null) {
            throw new AssertionError(
                    "bad OSR result: checksum=" + checksum + " sink=" + sink);
        }
        System.out.println("W002OsrProbe OK checksum=" + checksum);
    }
}
