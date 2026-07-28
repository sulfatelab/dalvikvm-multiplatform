public final class W002AttachProbe {
    private static final long BASE = 0x1234567800000000L;
    private static volatile Object sink;

    static {
        System.loadLibrary("w002attachprobe");
    }

    private static native int runAttachMatrix(int iterations);

    private static long attachedCallback(boolean daemon, int iteration) {
        Thread current = Thread.currentThread();
        if (current == null) {
            throw new AssertionError("Thread.currentThread returned null");
        }
        if (current.isDaemon() != daemon) {
            throw new AssertionError(
                    "daemon mismatch: expected=" + daemon + " actual=" + current.isDaemon());
        }

        Object[] allocations = new Object[8];
        for (int i = 0; i < allocations.length; ++i) {
            byte[] block = new byte[32 + i];
            block[0] = (byte) (iteration + i);
            allocations[i] = block;
        }
        sink = allocations;
        return BASE + (daemon ? 0x01000000L : 0L) + iteration;
    }

    public static void main(String[] args) {
        // Compile the callback before entering it from newly attached native threads.
        for (int i = 0; i < 2_000; ++i) {
            long value = attachedCallback(false, i & 7);
            if (value != BASE + (i & 7)) {
                throw new AssertionError("warmup value mismatch: " + value);
            }
        }

        int completed = runAttachMatrix(8);
        if (completed != 16 || sink == null) {
            throw new AssertionError("attach matrix failed: completed=" + completed);
        }
        System.out.println("W002AttachProbe OK completed=" + completed);
    }
}
