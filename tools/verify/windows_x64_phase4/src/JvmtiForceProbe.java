import dalvik.annotation.optimization.CriticalNative;
import dalvik.annotation.optimization.FastNative;

public final class JvmtiForceProbe {
    private static final String VALUES =
            "normalRegistered=137.75 fastRegistered=237.75 "
            + "criticalRegistered=337.75 normalDlsym=437.75 "
            + "fastDlsym=537.75 criticalDlsym=637.75";

    static {
        System.loadLibrary("jvmtiforceprobe");
    }

    private static native double normalRegistered(long a, double b, int c, float d);

    @FastNative
    private static native double fastRegistered(long a, double b, int c, float d);

    @CriticalNative
    private static native double criticalRegistered(long a, double b, int c, float d);

    private static native double normalDlsym(long a, double b, int c, float d);

    @FastNative
    private static native double fastDlsym(long a, double b, int c, float d);

    @CriticalNative
    private static native double criticalDlsym(long a, double b, int c, float d);

    private static native int setSingleStep(boolean enable);
    private static native long singleStepCount();

    private static String phaseValues(String phase) {
        double normalRegisteredValue = normalRegistered(10L, 20.5, 3, 4.25f);
        double fastRegisteredValue = fastRegistered(10L, 20.5, 3, 4.25f);
        double criticalRegisteredValue = criticalRegistered(10L, 20.5, 3, 4.25f);
        double normalDlsymValue = normalDlsym(10L, 20.5, 3, 4.25f);
        double fastDlsymValue = fastDlsym(10L, 20.5, 3, 4.25f);
        double criticalDlsymValue = criticalDlsym(10L, 20.5, 3, 4.25f);
        String values = "normalRegistered=" + normalRegisteredValue
                + " fastRegistered=" + fastRegisteredValue
                + " criticalRegistered=" + criticalRegisteredValue
                + " normalDlsym=" + normalDlsymValue
                + " fastDlsym=" + fastDlsymValue
                + " criticalDlsym=" + criticalDlsymValue;
        if (!VALUES.equals(values)) {
            throw new AssertionError(phase + " values: " + values);
        }
        if (phase != null) {
            System.out.println("JvmtiForceProbe " + phase + " " + values);
        }
        return values;
    }

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 200; ++i) {
            phaseValues(null);
        }
        Thread.sleep(100L);

        phaseValues("before");
        long beforeSteps = singleStepCount();
        int enableError = setSingleStep(true);
        if (enableError != 0) {
            throw new AssertionError("enable single-step failed: " + enableError);
        }

        phaseValues("during");
        long duringSteps = singleStepCount();
        if (duringSteps <= beforeSteps) {
            throw new AssertionError(
                    "single-step did not advance: before=" + beforeSteps + " during=" + duringSteps);
        }

        int disableError = setSingleStep(false);
        if (disableError != 0) {
            throw new AssertionError("disable single-step failed: " + disableError);
        }
        long disabledSteps = singleStepCount();
        phaseValues("after");
        long finalSteps = singleStepCount();
        if (finalSteps != disabledSteps) {
            throw new AssertionError(
                    "single-step continued after disable: disabled=" + disabledSteps
                    + " final=" + finalSteps);
        }

        System.out.println("JvmtiForceProbe steps before=" + beforeSteps
                + " during=" + duringSteps
                + " disabled=" + disabledSteps
                + " final=" + finalSteps);
        System.out.println("JvmtiForceProbe OK");
    }
}
