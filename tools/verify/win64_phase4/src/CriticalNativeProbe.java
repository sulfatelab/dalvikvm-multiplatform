import dalvik.annotation.optimization.CriticalNative;

public final class CriticalNativeProbe {
    private static volatile long sink;
    private static long longsResult;
    private static double doublesResult;
    private static double mixedResult;
    private static int mixed32Result;
    private static float floatReturnResult;
    private static boolean branchSeen;

    @CriticalNative
    private static native long zero();

    @CriticalNative
    private static native long sixLongs(long a, long b, long c, long d, long e, long f);

    @CriticalNative
    private static native double sixDoubles(
            double a, double b, double c, double d, double e, double f);

    @CriticalNative
    private static native double mixed(
            long a, double b, int c, double d, long e, double f);

    @CriticalNative
    private static native int mixed32(
            int a, float b, int c, float d, int e, float f);

    @CriticalNative
    private static native float floatReturn(float a, int b);

    private static native int calls();

    private static void exercise(boolean callNatives) {
        long value = sink;
        for (int i = 0; i < 1000000; ++i) {
            value = value * 1664525L + i + 1013904223L;
        }
        sink = value;
        if (!callNatives) {
            return;
        }
        branchSeen = true;

        // These calls must live in the warmed/compiled method. The interpreter's
        // temporary CriticalNative shorty bridge intentionally does not cover them.
        longsResult = zero() + sixLongs(1, 2, 3, 4, 5, 6);
        doublesResult = sixDoubles(1.0, 2.0, 3.0, 4.0, 5.0, 6.0);
        mixedResult = mixed(11, 2.5, 7, 4.25, 13, 6.75);
        mixed32Result = mixed32(3, 1.5f, 5, 2.5f, 7, 3.5f);
        floatReturnResult = floatReturn(1.25f, 7);
    }

    public static void main(String[] args) {
        // main() runs after this class is visibly initialized, so RegisterNatives
        // can publish direct CriticalNative entrypoints instead of retaining the
        // class-initialization dlsym gate.
        System.loadLibrary("criticalnativeprobe");
        exercise(false);
        exercise(true);

        System.out.println("CriticalNativeProbe values longs=" + longsResult
                + " doubles=" + doublesResult
                + " mixed=" + mixedResult
                + " mixed32=" + mixed32Result
                + " floatReturn=" + floatReturnResult
                + " calls=" + calls()
                + " branchSeen=" + branchSeen);

        if (longsResult != 190L) {
            throw new AssertionError("sixLongs ABI mismatch: " + longsResult);
        }
        if (Double.doubleToRawLongBits(doublesResult) != Double.doubleToRawLongBits(91.0)) {
            throw new AssertionError("sixDoubles ABI mismatch: " + doublesResult);
        }
        if (Double.doubleToRawLongBits(mixedResult) != Double.doubleToRawLongBits(159.5)) {
            throw new AssertionError("mixed ABI mismatch: " + mixedResult);
        }
        if (mixed32Result != 87) {
            throw new AssertionError("mixed32 ABI mismatch: " + mixed32Result);
        }
        if (Float.floatToRawIntBits(floatReturnResult) != Float.floatToRawIntBits(15.25f)) {
            throw new AssertionError("floatReturn ABI mismatch: " + floatReturnResult);
        }
        if (calls() != 63) {
            throw new AssertionError("CriticalNative functions not all called: " + calls());
        }
        if (!branchSeen) {
            throw new AssertionError("compiled CriticalNative branch was not executed");
        }
        System.out.println("CriticalNativeProbe OK");
    }
}
