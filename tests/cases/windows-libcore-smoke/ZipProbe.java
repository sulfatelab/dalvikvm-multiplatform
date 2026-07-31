import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.CRC32;
import java.util.zip.Deflater;
import java.util.zip.Inflater;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

/** L-003 zip edge matrix: DEFLATED multi-entry + ZipFile + Inflater/Deflater. */
public class ZipProbe {
  public static void main(String[] args) throws Exception {
    CRC32 crc = new CRC32();
    crc.update("zip-edge".getBytes("UTF-8"));
    System.out.println("crc32=" + Long.toHexString(crc.getValue()));
    if (crc.getValue() == 0) throw new RuntimeException("crc");

    byte[] raw = "deflate-roundtrip-0123456789".getBytes("UTF-8");
    Deflater def = new Deflater(Deflater.DEFAULT_COMPRESSION, true);
    def.setInput(raw); def.finish();
    byte[] defBuf = new byte[256];
    int dlen = def.deflate(defBuf); def.end();
    Inflater inf = new Inflater(true);
    inf.setInput(defBuf, 0, dlen);
    byte[] out = new byte[raw.length];
    int n = inf.inflate(out); inf.end();
    if (n != raw.length || !java.util.Arrays.equals(raw, out)) throw new RuntimeException("deflate");
    System.out.println("deflater.ok=true dlen=" + dlen);

    ByteArrayOutputStream baos = new ByteArrayOutputStream();
    ZipOutputStream zos = new ZipOutputStream(baos);
    String[] names = {"dir/a.txt", "dir/b.txt", "root.txt"};
    String[] bodies = {"alpha-content", "bravo-content", "root-payload-0123456789"};
    for (int i = 0; i < names.length; i++) {
      ZipEntry e = new ZipEntry(names[i]);
      e.setMethod(ZipEntry.DEFLATED);
      zos.putNextEntry(e);
      zos.write(bodies[i].getBytes("UTF-8"));
      zos.closeEntry();
    }
    zos.finish(); zos.close();
    byte[] zipBytes = baos.toByteArray();
    System.out.println("zip.bytes=" + zipBytes.length);

    Map<String,String> got = new HashMap<>();
    ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(zipBytes));
    int entries = 0; ZipEntry ze;
    while ((ze = zis.getNextEntry()) != null) {
      entries++;
      ByteArrayOutputStream o = new ByteArrayOutputStream();
      byte[] buf = new byte[64]; int r;
      while ((r = zis.read(buf)) > 0) o.write(buf, 0, r);
      got.put(ze.getName(), o.toString("UTF-8"));
      zis.closeEntry();
    }
    zis.close();
    System.out.println("zis.entries=" + entries);
    for (int i = 0; i < names.length; i++) {
      if (!bodies[i].equals(got.get(names[i]))) throw new RuntimeException("zis " + names[i]);
    }

    File tmp = new File("run/tmp_zip_edge.zip");
    tmp.getParentFile().mkdirs();
    try (FileOutputStream fos = new FileOutputStream(tmp)) { fos.write(zipBytes); }
    try (ZipFile zf = new ZipFile(tmp)) {
      Enumeration<? extends ZipEntry> en = zf.entries();
      int zn = 0;
      while (en.hasMoreElements()) {
        ZipEntry e = en.nextElement(); zn++;
        try (InputStream in = zf.getInputStream(e)) {
          ByteArrayOutputStream o = new ByteArrayOutputStream();
          byte[] buf = new byte[64]; int r;
          while ((r = in.read(buf)) > 0) o.write(buf, 0, r);
          if (!o.toString("UTF-8").equals(got.get(e.getName()))) throw new RuntimeException("zf " + e.getName());
        }
      }
      System.out.println("zipfile.entries=" + zn);
      if (zf.getEntry("root.txt") == null) throw new RuntimeException("missing root");
    }
    tmp.delete();
    System.out.println("ZipProbe.done=ok");
  }
}
