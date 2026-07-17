import java.math.BigInteger;

/** L-001: exercise libcore.math.NativeBN via java.math.BigInteger. */
public class BnProbe {
  public static void main(String[] args) {
    BigInteger a = new BigInteger("123456789012345678901234567890");
    BigInteger b = new BigInteger("987654321098765432109876543210");
    BigInteger sum = a.add(b);
    BigInteger prod = a.multiply(b);
    BigInteger mod = b.mod(a);
    BigInteger pow = a.modPow(BigInteger.valueOf(3), b);
    if (sum.signum() <= 0 || prod.signum() <= 0 || mod.signum() < 0 || pow.signum() < 0) {
      throw new AssertionError("unexpected BigInteger signs");
    }
    // Round-trip bitLength / toByteArray
    byte[] raw = prod.toByteArray();
    BigInteger back = new BigInteger(raw);
    if (!back.equals(prod)) {
      throw new AssertionError("toByteArray round-trip failed");
    }
    System.out.println("BnProbe.done=ok sum=" + sum + " mod=" + mod + " pow=" + pow);
  }
}
