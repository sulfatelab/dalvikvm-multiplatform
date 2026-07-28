import java.io.ByteArrayInputStream;
import javax.xml.parsers.SAXParser;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.Attributes;
import org.xml.sax.helpers.DefaultHandler;

/** L-001: exercise org.apache.harmony.xml.ExpatParser via SAX. */
public class XmlProbe {
  static final class Handler extends DefaultHandler {
    int elems;
    final StringBuilder text = new StringBuilder();
    @Override public void startElement(String uri, String localName, String qName, Attributes atts) {
      elems++;
    }
    @Override public void characters(char[] ch, int start, int length) {
      text.append(ch, start, length);
    }
  }

  public static void main(String[] args) throws Exception {
    SAXParserFactory f = SAXParserFactory.newInstance();
    f.setNamespaceAware(true);
    SAXParser p = f.newSAXParser();
    String xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        + "<root xmlns=\"urn:mdvm\"><item id=\"1\">hello</item><item id=\"2\">world</item></root>";
    Handler h = new Handler();
    p.parse(new ByteArrayInputStream(xml.getBytes("UTF-8")), h);
    if (h.elems < 3) {
      throw new AssertionError("expected root+2 items, got " + h.elems);
    }
    String t = h.text.toString().replaceAll("\\s+", "");
    if (!t.contains("hello") || !t.contains("world")) {
      throw new AssertionError("missing text: " + t);
    }
    System.out.println("XmlProbe.done=ok elems=" + h.elems + " text=" + t);
  }
}
