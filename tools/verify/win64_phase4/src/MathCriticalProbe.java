import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class MathCriticalProbe {
    private static final Method CEIL;
    private static final Method FLOOR;

    private static final double[] INPUTS = {
        Double.NEGATIVE_INFINITY,
        -Double.MAX_VALUE,
        -0x1.0p53,
        -12345.75,
        -1.5,
        -1.0,
        -0.9999999999999999,
        -Double.MIN_NORMAL,
        -Double.MIN_VALUE,
        -0.0,
        0.0,
        Double.MIN_VALUE,
        Double.MIN_NORMAL,
        0.1,
        0.5,
        0.9999999999999999,
        1.0,
        1.5,
        12345.75,
        0x1.0p53,
        Double.MAX_VALUE,
        Double.POSITIVE_INFINITY,
        Double.NaN,
    };

    static {
        try {
            CEIL = Math.class.getDeclaredMethod("ceil", double.class);
            FLOOR = Math.class.getDeclaredMethod("floor", double.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static void assertEquivalent(String operation, double input, double expected, double actual) {
        if (Double.isNaN(expected)) {
            if (!Double.isNaN(actual)) {
                throw new AssertionError(operation + " input=" + input + " expected NaN actual=" + actual);
            }
            return;
        }
        long expectedBits = Double.doubleToRawLongBits(expected);
        long actualBits = Double.doubleToRawLongBits(actual);
        if (expectedBits != actualBits) {
            throw new AssertionError(
                    operation + " input=" + input
                    + " expected=" + expected + " (0x" + Long.toHexString(expectedBits) + ")"
                    + " actual=" + actual + " (0x" + Long.toHexString(actualBits) + ")");
        }
    }

    private static long checkDirect(double input) {
        double expectedCeil = StrictMath.ceil(input);
        double expectedFloor = StrictMath.floor(input);
        double actualCeil = Math.ceil(input);
        double actualFloor = Math.floor(input);
        assertEquivalent("direct ceil", input, expectedCeil, actualCeil);
        assertEquivalent("direct floor", input, expectedFloor, actualFloor);
        return Double.doubleToLongBits(actualCeil) * 31L + Double.doubleToLongBits(actualFloor);
    }

    private static long checkReflective(double input) throws Exception {
        double expectedCeil = StrictMath.ceil(input);
        double expectedFloor = StrictMath.floor(input);
        double actualCeil = ((Double) CEIL.invoke(null, Double.valueOf(input))).doubleValue();
        double actualFloor = ((Double) FLOOR.invoke(null, Double.valueOf(input))).doubleValue();
        assertEquivalent("reflective ceil", input, expectedCeil, actualCeil);
        assertEquivalent("reflective floor", input, expectedFloor, actualFloor);
        return Double.doubleToLongBits(actualCeil) * 37L + Double.doubleToLongBits(actualFloor);
    }

    public static void main(String[] args) throws Exception {
        boolean ceilNative = Modifier.isNative(CEIL.getModifiers());
        boolean floorNative = Modifier.isNative(FLOOR.getModifiers());
        if (!ceilNative || !floorNative) {
            throw new AssertionError(
                    "Math surface not restored: ceilNative=" + ceilNative
                    + " floorNative=" + floorNative);
        }

        long checksum = 0L;
        for (double input : INPUTS) {
            checksum ^= checkReflective(input);
        }
        final int rounds = 2000;
        for (int round = 0; round < rounds; ++round) {
            for (double input : INPUTS) {
                checksum = Long.rotateLeft(checksum, 1) ^ checkDirect(input);
            }
        }

        System.out.println(
                "MathCriticalProbe native ceil=" + ceilNative
                + " floor=" + floorNative
                + " cases=" + INPUTS.length
                + " rounds=" + rounds
                + " checksum=0x" + Long.toHexString(checksum));
        System.out.println("MathCriticalProbe OK");
    }
}
