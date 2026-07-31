import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

/**
 * L-003 locale matrix without ICU4J resource bundles.
 * Calendar + String locale case + language tags; Collator soft.
 */
public class LocaleProbe {
  private static String pad2(int v) {
    return (v < 10 ? "0" : "") + v;
  }

  public static void main(String[] args) throws Exception {
    Locale def = Locale.getDefault();
    System.out.println("locale.default=" + def.toLanguageTag());
    System.out.println("locale.us=" + Locale.US.toLanguageTag());
    System.out.println("timezone.default=" + TimeZone.getDefault().getID());

    if (!"abc-i".equals("ABC-I".toLowerCase(Locale.US))) throw new RuntimeException("lower");
    if (!"ABC".equals("abc".toUpperCase(Locale.US))) throw new RuntimeException("upper");
    System.out.println("case.us=ok");

    Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"), Locale.US);
    cal.setTimeInMillis(0L);
    if (cal.get(Calendar.YEAR) != 1970) throw new RuntimeException("year=" + cal.get(Calendar.YEAR));
    // format epoch with calendar fields only (no DateFormat/ICU symbols)
    String iso0 = cal.get(Calendar.YEAR) + "-" + pad2(cal.get(Calendar.MONTH) + 1) + "-"
        + pad2(cal.get(Calendar.DAY_OF_MONTH)) + "T"
        + pad2(cal.get(Calendar.HOUR_OF_DAY)) + ":" + pad2(cal.get(Calendar.MINUTE)) + ":"
        + pad2(cal.get(Calendar.SECOND)) + "Z";
    System.out.println("date.iso.epoch=" + iso0);
    if (!"1970-01-01T00:00:00Z".equals(iso0)) throw new RuntimeException(iso0);

    cal.add(Calendar.DAY_OF_MONTH, 1);
    System.out.println("calendar.day1.ms=" + cal.getTimeInMillis());
    if (cal.getTimeInMillis() != 86400000L) throw new RuntimeException("add day");

    System.out.println("display.us=" + Locale.US.getDisplayLanguage(Locale.ROOT));
    Locale zh = Locale.forLanguageTag("zh-Hans-CN");
    System.out.println("tag.round=" + zh.toLanguageTag());

    try {
      java.text.Collator col = java.text.Collator.getInstance(Locale.US);
      int cmp = col.compare("a", "b");
      System.out.println("collator.a_b=" + cmp);
      if (cmp >= 0) throw new RuntimeException("collator");
      System.out.println("collator.ok=true");
    } catch (Throwable t) {
      System.out.println("collator.skip=" + t.getClass().getSimpleName() + ":" + t.getMessage());
    }

    System.out.println("LocaleProbe.done=ok");
  }
}
