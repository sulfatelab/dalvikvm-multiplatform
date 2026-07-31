import java.io.File;
import java.lang.reflect.Method;

/** Probe-only attributed coverage for the four ART quick callee-save frame families. */
public final class W003FrameProbe {
    private static volatile long sink;

    private static native void resetCounters();
    private static native long[] snapshotCounters();
    private static native int nativeEcho(Object marker, int value);

    private static String counts(long[] values) {
        if (values == null || values.length != 4) {
            throw new AssertionError("bad frame counter snapshot");
        }
        return "refs_only:" + values[0]
                + ",refs_and_args:" + values[1]
                + ",all_callee_saves:" + values[2]
                + ",everything:" + values[3];
    }

    private static void printPhase(String mode, String phase, long checksum, long[] values) {
        System.out.println("W003FrameProbe mode=" + mode
                + " phase=" + phase
                + " counts=" + counts(values)
                + " checksum=" + checksum);
    }

    private static long refsOnlyWork() throws InterruptedException {
        final Object lock = new Object();
        final int[] entered = new int[1];
        Runnable task = new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < 2000; ++i) {
                    synchronized (lock) {
                        entered[0]++;
                    }
                    if ((i & 63) == 0) {
                        Thread.yield();
                    }
                }
            }
        };
        Thread first = new Thread(task, "w003-lock-first");
        Thread second = new Thread(task, "w003-lock-second");
        first.start();
        second.start();

        long allocationChecksum = 0;
        for (int i = 0; i < 4096; ++i) {
            byte[] bytes = new byte[4096 + (i & 255)];
            bytes[0] = (byte)i;
            allocationChecksum += bytes.length + bytes[0];
        }
        first.join();
        second.join();
        if (entered[0] != 4000) {
            throw new AssertionError("monitor workload lost entries: " + entered[0]);
        }
        return allocationChecksum + entered[0];
    }

    private static long refsAndArgsWork() {
        Object marker = new Object();
        long checksum = 0;
        for (int i = 0; i < 2000; ++i) {
            checksum += nativeEcho(marker, i);
        }
        if (checksum != 2001000L) {
            throw new AssertionError("generic JNI checksum=" + checksum);
        }
        return checksum;
    }

    private static int classCastWork() {
        int caught = 0;
        for (int i = 0; i < 1000; ++i) {
            try {
                String ignored = (String)(Object)new Object();
                sink += ignored.length();
            } catch (ClassCastException expected) {
                caught++;
            }
        }
        if (caught != 1000) {
            throw new AssertionError("class-cast workload caught=" + caught);
        }
        return caught;
    }

    private static int arrayStoreWork() {
        int caught = 0;
        for (int i = 0; i < 1000; ++i) {
            try {
                Object[] array = new String[1];
                array[0] = new Object();
            } catch (ArrayStoreException expected) {
                caught++;
            }
        }
        if (caught != 1000) {
            throw new AssertionError("array-store workload caught=" + caught);
        }
        return caught;
    }

    private static int boundsWork() {
        int caught = 0;
        for (int i = 0; i < 1000; ++i) {
            try {
                int[] array = new int[1];
                sink += array[2];
            } catch (ArrayIndexOutOfBoundsException expected) {
                caught++;
            }
        }
        if (caught != 1000) {
            throw new AssertionError("bounds workload caught=" + caught);
        }
        return caught;
    }

    // Keep implicit-null faults out of this frame-family probe. Windows x64 nterp
    // fault-to-NPE translation belongs to W-010 and is independently open.
    private static int allCalleeSavesWork(String mode) {
        int caught = classCastWork();
        printPhase(mode, "all_callee_saves_class_cast", caught, snapshotCounters());
        caught += arrayStoreWork();
        printPhase(mode, "all_callee_saves_array_store", caught, snapshotCounters());
        caught += boundsWork();
        printPhase(mode, "all_callee_saves_bounds", caught, snapshotCounters());
        return caught;
    }

    private static long tracedWork(int value) {
        long result = value * 17L + 3L;
        result ^= Long.rotateLeft(result, value & 31);
        sink = result;
        return result;
    }

    private static long[] everythingWork() throws Exception {
        File traceFile = new File("w003-frame.trace");
        traceFile.delete();
        Class<?> vmDebug = Class.forName("dalvik.system.VMDebug");
        Method start = vmDebug.getMethod(
                "startMethodTracing",
                String.class,
                int.class,
                int.class,
                boolean.class,
                int.class);
        Method stop = vmDebug.getMethod("stopMethodTracing");

        boolean started = false;
        long checksum = 0;
        long[] values;
        try {
            start.invoke(null, traceFile.getPath(), 1024 * 1024, 0, false, 0);
            started = true;
            resetCounters();
            for (int i = 0; i < 2000; ++i) {
                checksum += tracedWork(i);
            }
            values = snapshotCounters();
        } finally {
            if (started) {
                stop.invoke(null);
            }
        }
        if (!(traceFile.delete() || !traceFile.exists())) {
            throw new AssertionError("failed to delete " + traceFile);
        }
        sink = checksum;
        return values;
    }

    public static void main(String[] args) throws Exception {
        System.loadLibrary("w003frameprobe");
        String mode = System.getProperty("w003.mode", "unknown");

        for (int i = 0; i < 20000; ++i) {
            tracedWork(i);
        }

        resetCounters();
        long refsOnlyChecksum = refsOnlyWork();
        printPhase(mode, "refs_only", refsOnlyChecksum, snapshotCounters());

        resetCounters();
        long refsAndArgsChecksum = refsAndArgsWork();
        printPhase(mode, "refs_and_args", refsAndArgsChecksum, snapshotCounters());

        resetCounters();
        long allCalleeSavesChecksum = allCalleeSavesWork(mode);
        printPhase(mode, "all_callee_saves", allCalleeSavesChecksum, snapshotCounters());

        long[] everythingCounts = everythingWork();
        printPhase(mode, "everything", sink, everythingCounts);

        long finalChecksum = refsOnlyChecksum
                ^ refsAndArgsChecksum
                ^ allCalleeSavesChecksum
                ^ sink;
        System.out.println("W003FrameProbe OK mode=" + mode + " checksum=" + finalChecksum);
    }
}
