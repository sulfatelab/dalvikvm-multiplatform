public final class W039BootOatUnwindCorruptionProbe {
  private static native boolean nativeAudit();

  public static void main(String[] args) {
    System.loadLibrary("w039aotunwindcorruptionprobe");
    if (!nativeAudit()) {
      throw new AssertionError("native AOT unwind corruption audit returned false");
    }
    System.out.println("W039BootOatUnwindCorruptionProbe PASS");
  }
}
