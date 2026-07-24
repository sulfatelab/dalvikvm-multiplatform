import dalvik.annotation.optimization.CriticalNative;

public final class CriticalNativeDlsymProbe {
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

    @CriticalNative
    private static native int callMask();

    public static void exercise(boolean callNatives) {
        long value = CriticalNativeProbe.getSink();
        for (int i = 0; i < 1000000; ++i) {
            value = value * 1103515245L + i + 12345L;
        }
        CriticalNativeProbe.setSink(value);
        if (!callNatives) {
            return;
        }
        branchSeen = true;

        longsResult = zero() + sixLongs(1, 2, 3, 4, 5, 6);
        doublesResult = sixDoubles(1.0, 2.0, 3.0, 4.0, 5.0, 6.0);
        mixedResult = mixed(11, 2.5, 7, 4.25, 13, 6.75);
        mixed32Result = mixed32(3, 1.5f, 5, 2.5f, 7, 3.5f);
        floatReturnResult = floatReturn(1.25f, 7);
    }

    public static void verify() {
        verify("");
    }

    public static void verify(String phase) {
        String label = phase.isEmpty()
                ? "CriticalNativeDlsymProbe values"
                : "CriticalNativeDlsymProbe " + phase + " values";
        System.out.println(label + " longs=" + longsResult
                + " doubles=" + doublesResult
                + " mixed=" + mixedResult
                + " mixed32=" + mixed32Result
                + " floatReturn=" + floatReturnResult
                + " calls=" + callMask()
                + " branchSeen=" + branchSeen);

        if (longsResult != 190L) {
            throw new AssertionError("dlsym sixLongs ABI mismatch: " + longsResult);
        }
        if (Double.doubleToRawLongBits(doublesResult) != Double.doubleToRawLongBits(91.0)) {
            throw new AssertionError("dlsym sixDoubles ABI mismatch: " + doublesResult);
        }
        if (Double.doubleToRawLongBits(mixedResult) != Double.doubleToRawLongBits(159.5)) {
            throw new AssertionError("dlsym mixed ABI mismatch: " + mixedResult);
        }
        if (mixed32Result != 87) {
            throw new AssertionError("dlsym mixed32 ABI mismatch: " + mixed32Result);
        }
        if (Float.floatToRawIntBits(floatReturnResult) != Float.floatToRawIntBits(15.25f)) {
            throw new AssertionError("dlsym floatReturn ABI mismatch: " + floatReturnResult);
        }
        if (callMask() != 63) {
            throw new AssertionError("dlsym CriticalNative functions not all called: " + callMask());
        }
        if (!branchSeen) {
            throw new AssertionError("compiled dlsym CriticalNative branch was not executed");
        }
        System.out.println(phase.isEmpty()
                ? "CriticalNativeDlsymProbe OK"
                : "CriticalNativeDlsymProbe " + phase + " OK");
    }
}
