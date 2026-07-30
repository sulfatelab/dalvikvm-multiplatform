/** Focused Microsoft-x64 XMM6-XMM15 preservation probe around JNI quick invoke. */
public final class W003XmmSentinelProbe {
    private static native int runXmmSentinel(int expected, boolean clobberForSelfTest);
    private static native void runXmmExceptionSentinel(boolean clobberForSelfTest);
    private static native int getXmmExceptionMask();

    private static final class Cell {
        int value;
    }

    private static int managedCallback(
            double a0, double a1, double a2, double a3,
            double a4, double a5, double a6, double a7,
            double a8, double a9, double a10, double a11) {
        double p0 = a0 * 1.125 + a6;
        double p1 = a1 * 1.25 + a7;
        double p2 = a2 * 1.375 + a8;
        double p3 = a3 * 1.5 + a9;
        double p4 = a4 * 1.625 + a10;
        double p5 = a5 * 1.75 + a11;
        double p6 = a6 * 1.875 - a0;
        double p7 = a7 * 2.0 - a1;
        double p8 = a8 * 2.125 - a2;
        double p9 = a9 * 2.25 - a3;
        double p10 = a10 * 2.375 - a4;
        double p11 = a11 * 2.5 - a5;

        long h0 = Double.doubleToRawLongBits(p0 * p7 + p11);
        long h1 = Double.doubleToRawLongBits(p1 * p8 + p6);
        long h2 = Double.doubleToRawLongBits(p2 * p9 + p7);
        long h3 = Double.doubleToRawLongBits(p3 * p10 + p8);
        long h4 = Double.doubleToRawLongBits(p4 * p11 + p9);
        long h5 = Double.doubleToRawLongBits(p5 * p6 + p10);
        long mixed = h0 ^ Long.rotateLeft(h1, 7) ^ Long.rotateLeft(h2, 13)
                ^ Long.rotateLeft(h3, 21) ^ Long.rotateLeft(h4, 29)
                ^ Long.rotateLeft(h5, 37);
        return (int) (mixed ^ (mixed >>> 32));
    }

    private static int managedExceptionCallback(
            Cell cell,
            double a0, double a1, double a2, double a3,
            double a4, double a5, double a6, double a7,
            double a8, double a9, double a10, double a11) {
        int checksum = managedCallback(
                a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11);
        return checksum ^ cell.value;
    }

    private static int expectedValue() {
        return managedCallback(
                1.25, -2.5, 3.75, -4.125,
                5.5, -6.625, 7.75, -8.875,
                9.0, -10.25, 11.5, -12.75);
    }

    public static void main(String[] args) {
        System.loadLibrary("w003xmmsentinel");
        String mode = System.getProperty("w003.mode", "unknown");
        int expected = expectedValue();
        int warmChecksum = 0;
        for (int i = 0; i < 20000; ++i) {
            warmChecksum ^= expectedValue() + i;
        }

        int mask = 0;
        int iterations = 128;
        for (int i = 0; i < iterations; ++i) {
            mask |= runXmmSentinel(expected, false);
        }
        int fullSelfTestMask = runXmmSentinel(expected, true);
        int selfTestMask = fullSelfTestMask & 0x3f;
        int exceptionMask = 0;
        int exceptionCaught = 0;
        int exceptionIterations = 32;
        for (int i = 0; i < exceptionIterations; ++i) {
            try {
                runXmmExceptionSentinel(false);
                throw new AssertionError("exception sentinel returned without NPE");
            } catch (NullPointerException expectedException) {
                ++exceptionCaught;
                exceptionMask |= getXmmExceptionMask();
            }
        }
        int exceptionSelfTestMask;
        try {
            runXmmExceptionSentinel(true);
            throw new AssertionError("exception sentinel self-test returned without NPE");
        } catch (NullPointerException expectedException) {
            exceptionSelfTestMask = getXmmExceptionMask();
        }
        System.out.println("W003XmmSentinelProbe mode=" + mode
                + " expected=" + expected
                + " warmChecksum=" + warmChecksum
                + " mask=" + mask
                + " selfTestMask=" + selfTestMask
                + " iterations=" + iterations
                + " fullSelfTestMask=" + fullSelfTestMask
                + " exceptionMask=" + exceptionMask
                + " exceptionCaught=" + exceptionCaught
                + " exceptionIterations=" + exceptionIterations
                + " exceptionSelfTestMask=" + exceptionSelfTestMask);
        if (mask != 0) {
            throw new AssertionError("XMM sentinel mismatch mask=0x"
                    + Integer.toHexString(mask));
        }
        if (fullSelfTestMask != 0x3ff) {
            throw new AssertionError("XMM sentinel self-test mismatch mask=0x"
                    + Integer.toHexString(fullSelfTestMask));
        }
        if (exceptionMask != 0 || exceptionCaught != exceptionIterations) {
            throw new AssertionError("XMM exception sentinel mismatch mask=0x"
                    + Integer.toHexString(exceptionMask)
                    + " caught=" + exceptionCaught);
        }
        if (exceptionSelfTestMask != 0x3ff) {
            throw new AssertionError("XMM exception sentinel self-test mismatch mask=0x"
                    + Integer.toHexString(exceptionSelfTestMask));
        }
        System.out.println("W003XmmSentinelProbe OK");
    }
}
