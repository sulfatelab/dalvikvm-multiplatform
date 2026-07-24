import dalvik.annotation.optimization.FastNative;

/** Focused Win64 compiled-JNI normal/FastNative argument and binding-transition probe. */
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
    private static native void unregisterNatives();
    private static native void registerAlternateNatives();

    private static final class Results {
        double normalRegistered;
        double fastRegistered;
        double normalDlsym;
        double fastDlsym;
        double normalInstance;
        double fastInstance;
    }

    private static Results runCalls(FastNativeAbiProbe probe, Object marker) {
        Results results = new Results();
        for (int iteration = 0; iteration < 1000; ++iteration) {
            results.normalRegistered = normalRegistered(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            results.fastRegistered = fastRegistered(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            results.normalDlsym = normalDlsym(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19, true);
            results.fastDlsym = fastDlsym(
                    11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19, true);
            results.normalInstance = probe.normalInstance(
                    marker, 11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
            results.fastInstance = probe.fastInstance(
                    marker, 11, 2.5, 7, 4.25f, 13, 6.75, 17, 8.5f, 9.25, 10.5, 19);
        }
        return results;
    }

    private static void checkValue(double actual, double expected, String name) {
        if (Double.doubleToRawLongBits(actual) != Double.doubleToRawLongBits(expected)) {
            throw new AssertionError(name + " mismatch: " + actual + " != " + expected);
        }
    }

    private static void checkPhase(Results results, double phaseOffset, String phase) {
        checkValue(results.normalRegistered, BASE_VALUE + phaseOffset, phase + ".normalRegistered");
        checkValue(results.fastRegistered,
                BASE_VALUE + phaseOffset + 1000.0, phase + ".fastRegistered");
        checkValue(results.normalDlsym,
                BASE_VALUE + phaseOffset + 2012.0, phase + ".normalDlsym");
        checkValue(results.fastDlsym,
                BASE_VALUE + phaseOffset + 3012.0, phase + ".fastDlsym");
        checkValue(results.normalInstance,
                BASE_VALUE + phaseOffset + 4000.0, phase + ".normalInstance");
        checkValue(results.fastInstance,
                BASE_VALUE + phaseOffset + 5000.0, phase + ".fastInstance");
        if (callMask() != 63) {
            throw new AssertionError(phase + " native ABI functions not all called: " + callMask());
        }
    }

    private static void printPhase(Results results, String phase) {
        System.out.println("FastNativeAbiProbe " + phase
                + " normalRegistered=" + results.normalRegistered
                + " fastRegistered=" + results.fastRegistered
                + " normalDlsym=" + results.normalDlsym
                + " fastDlsym=" + results.fastDlsym
                + " normalInstance=" + results.normalInstance
                + " fastInstance=" + results.fastInstance
                + " calls=" + callMask());
    }

    public static void main(String[] args) {
        System.loadLibrary("nativeabiprobe");

        FastNativeAbiProbe probe = new FastNativeAbiProbe();
        Object marker = new Object();

        Results initial = runCalls(probe, marker);
        checkPhase(initial, 0.0, "initial");
        printPhase(initial, "initial");

        unregisterNatives();
        Results unregistered = runCalls(probe, marker);
        checkPhase(unregistered, 10000.0, "unregistered");
        printPhase(unregistered, "unregistered");

        registerAlternateNatives();
        Results reregistered = runCalls(probe, marker);
        checkPhase(reregistered, 20000.0, "reregistered");
        printPhase(reregistered, "reregistered");

        System.out.println("FastNativeAbiProbe OK");
    }
}
