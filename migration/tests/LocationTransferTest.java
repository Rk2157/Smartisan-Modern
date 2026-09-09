import android.location.Location;
import com.amap.api.location.AMapLocation;
import com.fuck.android.rimet.modern.LocationTransfer;

public final class LocationTransferTest {
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        AMapLocation saved = new AMapLocation();
        saved.setLatitude(31.2); saved.setLongitude(121.5); saved.setAltitude(4);
        saved.setAccuracy(5); saved.setCity("Shanghai"); saved.setNumber("8");
        ClassLoader targetLoader = new ClassLoader(LocationTransferTest.class.getClassLoader()) {
            @Override protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                if (!name.equals("com.amap.api.location.AMapLocation")) return super.loadClass(name, resolve);
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    try (java.io.InputStream stream = getParent().getResourceAsStream(name.replace('.', '/')+".class")) {
                        byte[] bytes = stream.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);
                    } catch (java.io.IOException error) { throw new ClassNotFoundException(name, error); }
                }
                if (resolve) resolveClass(result);
                return result;
            }
        };
        Class<?> targetClass = targetLoader.loadClass("com.amap.api.location.AMapLocation");
        Object copy = LocationTransfer.copy(targetClass, saved, null, false);
        check(targetClass.isInstance(copy), "target classloader owns returned value");
        check(!(copy instanceof AMapLocation), "same class name does not imply assignment compatibility");
        check(((Location)copy).getLatitude()==31.2 && ((Location)copy).getLongitude()==121.5, "coordinates retained");
        check(((Location)copy).getAltitude()==4 && ((Location)copy).getAccuracy()==5, "altitude/accuracy retained");
        check("Shanghai".equals(targetClass.getMethod("getCity").invoke(copy)), "SDK detail copied");
        check("8".equals(targetClass.getMethod("getStreetNum").invoke(copy)), "asymmetric SDK getter/setter supported");
        for (int i=0; i<100; i++) {
            Location shifted = (Location) LocationTransfer.copy(targetClass, saved, copy, true);
            check(Math.abs(shifted.getLatitude()-31.2)<0.000046, "latitude offset bounded");
            check(Math.abs(shifted.getLongitude()-121.5)<0.000054, "longitude offset bounded");
        }
        check(saved.getLatitude()==31.2 && saved.getLongitude()==121.5, "snapshot is never mutated");
        check(((Location)copy).getLatitude()==31.2 && ((Location)copy).getLongitude()==121.5, "incoming location is never mutated");
        System.out.println("PASS: cross-classloader location conversion, SDK fields, bounded jitter and snapshot immutability");
    }
}
