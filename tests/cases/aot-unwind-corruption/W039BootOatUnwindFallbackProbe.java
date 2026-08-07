public final class W039BootOatUnwindFallbackProbe {
  private static native boolean nativeVerifyImageless();

  public static void main(String[] args) {
    System.loadLibrary("w039aotunwindcorruptionprobe");
    if (!nativeVerifyImageless()) {
      throw new AssertionError("native AOT unwind fallback audit returned false");
    }
  }
}
