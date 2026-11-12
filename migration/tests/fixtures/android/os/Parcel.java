package android.os;

/** Small string-only parcel fixture; Android Parcel wire-format validation is separate. */
public final class Parcel {
    private byte[] bytes = new byte[0];
    public static Parcel obtain() { return new Parcel(); }
    public void unmarshall(byte[] data, int offset, int length) {
        bytes = java.util.Arrays.copyOfRange(data, offset, offset + length);
    }
    public byte[] marshall() { return bytes.clone(); }
    public void setDataPosition(int position) {
        if (position != 0) throw new AssertionError("fixture supports position zero only");
    }
    public void writeString(String text) {
        bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
    public String readString() {
        return new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
    }
    public void recycle() {}
}
