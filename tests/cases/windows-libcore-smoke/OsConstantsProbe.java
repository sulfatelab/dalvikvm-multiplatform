import android.system.OsConstants;

/** L-001: OsConstantsHolder-backed fields + hardcoded Linux ABI AF/SOCK. */
public class OsConstantsProbe {
  static void check(String name, boolean ok, int v) {
    System.out.println((ok ? "PASS " : "FAIL ") + name + "=" + v + (ok ? "" : " (unexpected)"));
    if (!ok) throw new AssertionError(name + "=" + v);
  }

  public static void main(String[] args) {
    // Hardcoded in OsConstants static block (not Holder)
    check("AF_INET", OsConstants.AF_INET == 2, OsConstants.AF_INET);
    check("AF_INET6", OsConstants.AF_INET6 == 10, OsConstants.AF_INET6);
    check("SOCK_STREAM", OsConstants.SOCK_STREAM == 1, OsConstants.SOCK_STREAM);
    check("EAGAIN", OsConstants.EAGAIN == 11, OsConstants.EAGAIN);

    // Holder-backed — bionic/glibc AI flags used by win_net mapping
    check("AI_PASSIVE", OsConstants.AI_PASSIVE == 0x1, OsConstants.AI_PASSIVE);
    check("AI_NUMERICHOST", OsConstants.AI_NUMERICHOST == 0x4, OsConstants.AI_NUMERICHOST);
    check("AI_ADDRCONFIG", OsConstants.AI_ADDRCONFIG == 0x20, OsConstants.AI_ADDRCONFIG);
    check("AI_CANONNAME", OsConstants.AI_CANONNAME == 0x2, OsConstants.AI_CANONNAME);
    check("AI_V4MAPPED", OsConstants.AI_V4MAPPED == 0x8, OsConstants.AI_V4MAPPED);

    check("EAI_NONAME", OsConstants.EAI_NONAME == -2, OsConstants.EAI_NONAME);
    check("EAI_AGAIN", OsConstants.EAI_AGAIN == -3, OsConstants.EAI_AGAIN);

    check("O_DIRECT", OsConstants.O_DIRECT == 0x4000, OsConstants.O_DIRECT);
    check("SIGRTMIN", OsConstants.SIGRTMIN == 32, OsConstants.SIGRTMIN);
    check("_SC_NPROCESSORS_CONF", OsConstants._SC_NPROCESSORS_CONF == 83, OsConstants._SC_NPROCESSORS_CONF);
    check("_SC_NPROCESSORS_ONLN", OsConstants._SC_NPROCESSORS_ONLN == 84, OsConstants._SC_NPROCESSORS_ONLN);
    check("_SC_PAGESIZE", OsConstants._SC_PAGESIZE == 30, OsConstants._SC_PAGESIZE);

    // Non-zero / non-default smoke for a few more holder fields
    check("NI_NUMERICHOST", OsConstants.NI_NUMERICHOST == 1, OsConstants.NI_NUMERICHOST);
    check("F_GETLK", OsConstants.F_GETLK == 5, OsConstants.F_GETLK);

    System.out.println("OsConstantsProbe.done=ok");
  }
}
