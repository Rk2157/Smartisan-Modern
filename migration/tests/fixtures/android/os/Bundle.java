package android.os;

/** Only the identity and simple values of extras are needed by JVM contract tests. */
public class Bundle {
    private final java.util.Map<String, String> values = new java.util.HashMap<>();
    public Bundle() {}
    public Bundle(Bundle source) { values.putAll(source.values); }
    public void putString(String key, String value) { values.put(key, value); }
    public String getString(String key) { return values.get(key); }
}
