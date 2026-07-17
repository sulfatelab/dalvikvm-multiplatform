import java.security.MessageDigest;
import java.security.Provider;
import java.security.SecureRandom;
import java.security.Security;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;

/**
 * L-002 C2 smoke: conscrypt OpenSSLProvider must be on the default provider list
 * and load native libjavacrypto. Not a full HTTPS handshake (that is C3).
 */
public class SslProviderProbe {
  public static void main(String[] args) throws Exception {
    System.out.println("mapLibraryName.javacrypto=" + System.mapLibraryName("javacrypto"));

    Provider[] providers = Security.getProviders();
    System.out.println("providers.count=" + providers.length);
    for (int i = 0; i < providers.length; i++) {
      Provider p = providers[i];
      System.out.println("provider." + (i + 1) + "=" + p.getName() + " class=" + p.getClass().getName());
    }

    Provider aos = Security.getProvider("AndroidOpenSSL");
    System.out.println("AndroidOpenSSL=" + (aos != null ? aos.getClass().getName() : "null"));

    // Force a conscrypt-backed algorithm
    MessageDigest md = MessageDigest.getInstance("SHA-256");
    System.out.println("sha256.provider=" + md.getProvider().getName());
    byte[] dig = md.digest("hello-conscrypt".getBytes("UTF-8"));
    StringBuilder hex = new StringBuilder();
    for (byte b : dig) hex.append(String.format("%02x", b));
    System.out.println("sha256.hex=" + hex);

    SecureRandom sr = SecureRandom.getInstance("SHA1PRNG");
    System.out.println("securerandom.provider=" + sr.getProvider().getName());

    try {
      Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
      System.out.println("aesgcm.provider=" + c.getProvider().getName());
    } catch (Throwable t) {
      System.out.println("aesgcm.error=" + t.getClass().getName() + ": " + t.getMessage());
    }

    SSLContext ctx = SSLContext.getInstance("TLS");
    System.out.println("sslcontext.protocol=" + ctx.getProtocol());
    System.out.println("sslcontext.provider=" + ctx.getProvider().getName());
    ctx.init(null, null, null);
    System.out.println("sslcontext.init=ok");
    System.out.println("SslProviderProbe.done=ok");
  }
}
