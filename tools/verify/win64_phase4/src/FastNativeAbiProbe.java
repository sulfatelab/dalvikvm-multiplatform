import dalvik.annotation.optimization.FastNative;

/** Focused Win64 compiled-JNI normal/FastNative argument mapping probe. */
public final class FastNativeAbiProbe {
    private static final double BASE_VALUE = 743.75;

    private static native double normalRegistered(
            long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k);

    @FastNative
    private static native double fastRegistered(
            long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k);

    private static native double normalDlsym(
            long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k, boolean l);

    @FastNative
    private static native double fastDlsym(
            long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k, boolean l);

    private native double normalInstance(
            Object marker, long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k);

    @FastNative
    private native double fastInstance(
            Object marker, long a, double b, int c, float d, long e, double f,
            int g, float h, double i, double j, int k);

    private static native int callMask();

    private static void checkValue(double actual, double expected, String name) {
        if (Double.doubleToRawLongBits(actual) != Double.doubleToRawLongBits(expected)) {
            throw new AssertionError(name + " mismatch: " + actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        System.loadLibrary("nativeabiprobe");

        FastNativeAbiProbe probe = new FastNativeAbiProbe();
        Object marker = new Object();
        double normalRegisteredResult = 0.0;
        double fastRegisteredResult = 0.0;
        double normalDlsymResult = 0.0;
        double fastDlsymResult = 0.0;
        double normalInstanceResult = 0.0;
        double fastInstanceResult = 0.0;

        for (int iteration = 0; iteration < 1000; ++iteration) {
            normalRegisteredResult = normalRegistered(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            fastRegisteredResult = fastRegistered(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            normalDlsymResult = normalDlsym(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19, true);
            fastDlsymResult = fastDlsym(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19, true);
            normalInstanceResult = probe.normalInstance(
                    marker, 11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            fastInstanceResult = probe.fastInstance(
                    marker, 11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
        }

        checkValue(normalRegisteredResult, BASE_VALUE, "normalRegistered");
        checkValue(fastRegisteredResult, BASE_VALUE + 1000.0, "fastRegistered");
        checkValue(normalDlsymResult, BASE_VALUE + 2012.0, "normalDlsym");
        checkValue(fastDlsymResult, BASE_VALUE + 3012.0, "fastDlsym");
        checkValue(normalInstanceResult, BASE_VALUE + 4000.0, "normalInstance");
        checkValue(fastInstanceResult, BASE_VALUE + 5000.0, "fastInstance");
        if (callMask() != 63) {
            throw new AssertionError("native ABI functions not all called: " + callMask());
        }

        System.out.println("FastNativeAbiProbe values normalRegistered=" + normalRegisteredResult
                + " fastRegistered=" + fastRegisteredResult
                + " normalDlsym=" + normalDlsymResult
                + " fastDlsym=" + fastDlsymResult
                + " normalInstance=" + normalInstanceResult
                + " fastInstance=" + fastInstanceResult
                + " calls=" + callMask());
        System.out.println("FastNativeAbiProbe OK");
    }
}
