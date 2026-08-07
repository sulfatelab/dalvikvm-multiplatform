import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public final class W038BootOatFatalUnwindProbe {
  private static native int nativeArmFatal(Method[] candidates);
  private static native void nativeCrash();

  private static Method method(Class<?> owner, String name, Class<?>... parameters)
      throws ReflectiveOperationException {
    return owner.getDeclaredMethod(name, parameters);
  }

  private static Method[] candidates() throws ReflectiveOperationException {
    return new Method[] {
      method(Arrays.class, "sort", Object[].class, Comparator.class),
      method(Arrays.class, "sort", Object[].class, int.class, int.class, Comparator.class),
      method(Collections.class, "sort", List.class, Comparator.class),
      method(ArrayList.class, "sort", Comparator.class),
    };
  }

  private static void primeCandidates() {
    Comparator<Integer> comparator = Integer::compare;
    Integer[] first = {2, 1};
    Arrays.sort(first, comparator);
    Integer[] second = {4, 3};
    Arrays.sort(second, 0, second.length, comparator);
    List<Integer> third = new ArrayList<>(Arrays.asList(6, 5));
    Collections.sort(third, comparator);
    List<Integer> fourth = new ArrayList<>(Arrays.asList(8, 7));
    fourth.sort(comparator);
  }

  private static void invokeSelected(int selected, Comparator<Integer> comparator) {
    switch (selected) {
      case 0:
        Arrays.sort(new Integer[] {2, 1}, comparator);
        return;
      case 1:
        Integer[] values = {4, 3};
        Arrays.sort(values, 0, values.length, comparator);
        return;
      case 2:
        Collections.sort(new ArrayList<>(Arrays.asList(6, 5)), comparator);
        return;
      case 3:
        new ArrayList<>(Arrays.asList(8, 7)).sort(comparator);
        return;
      default:
        throw new AssertionError("native probe selected an unknown fatal method: " + selected);
    }
  }

  public static void main(String[] args) throws Exception {
    System.loadLibrary("w038aotunwindprobe");
    primeCandidates();
    int selected = nativeArmFatal(candidates());
    Comparator<Integer> crashingComparator =
        (left, right) -> {
          nativeCrash();
          return Integer.compare(left, right);
        };
    invokeSelected(selected, crashingComparator);
    System.out.println("W038_FATAL_UNEXPECTED_RETURN selected=" + selected);
    System.out.flush();
    throw new AssertionError("fatal boot-OAT callback unexpectedly returned");
  }
}
