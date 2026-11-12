import android.location.Location;
import android.os.Bundle;
import com.alibaba.android.rimet.LocationService.ServiceType;
import com.alibaba.android.rimet.model.DtLocation;
import com.amap.api.location.AMapLocation;
import com.fuck.android.rimet.modern.LocationTransfer;

public final class LocationTransferTest {
    /** Some SDK versions include LocationDetail in nonzero-error diagnostics. */
    public static final class DerivedErrorLocation extends DtLocation {
        public DerivedErrorLocation(String provider) { super(provider); }
        @Override public String getErrorInfo() {
            return getErrorCode()==0 ? super.getErrorInfo() : super.getErrorInfo()+"|"+getLocationDetail();
        }
    }
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        AMapLocation saved = new AMapLocation();
        saved.setLatitude(31.2); saved.setLongitude(121.5); saved.setAltitude(4);
        saved.setAccuracy(5); saved.setCity("Shanghai"); saved.setNumber("8");
        saved.setErrorCode(3); saved.setErrorInfo("snapshot-status"); saved.setLocationType(2);
        saved.setLocationDetail("snapshot-location-detail");
        saved.setTrustedLevel(4); saved.setCoordType("GCJ02"); saved.setConScenario(5);
        Bundle savedExtras = new Bundle(); savedExtras.putString("origin", "snapshot"); saved.setExtras(savedExtras);
        ClassLoader targetLoader = new ClassLoader(LocationTransferTest.class.getClassLoader()) {
            @Override protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                if (!name.equals("com.amap.api.location.AMapLocation") && !name.equals("com.alibaba.android.rimet.model.DtLocation"))
                    return super.loadClass(name, resolve);
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
        check(((Location)copy).getExtras()==savedExtras, "legacy SDK copy retains snapshot extras behavior");
        check(((Integer)targetClass.getMethod("getErrorCode").invoke(copy))==3 &&
                "snapshot-status".equals(targetClass.getMethod("getErrorInfo").invoke(copy)) &&
                ((Integer)targetClass.getMethod("getLocationType").invoke(copy))==2,
                "legacy SDK copy retains snapshot result status behavior");
        check("snapshot-location-detail".equals(targetClass.getMethod("getLocationDetail").invoke(copy)),
                "legacy SDK copy retains snapshot location diagnostic details");
        for (int i=0; i<100; i++) {
            Location shifted = (Location) LocationTransfer.copy(targetClass, saved, copy, true);
            check(Math.abs(shifted.getLatitude()-31.2)<0.000046, "latitude offset bounded");
            check(Math.abs(shifted.getLongitude()-121.5)<0.000054, "longitude offset bounded");
        }
        check(saved.getLatitude()==31.2 && saved.getLongitude()==121.5, "snapshot is never mutated");
        check(((Location)copy).getLatitude()==31.2 && ((Location)copy).getLongitude()==121.5, "incoming location is never mutated");
        Class<?> dtoType = targetLoader.loadClass("com.alibaba.android.rimet.model.DtLocation");
        Object dto = dtoType.getConstructor(String.class).newInstance("network");
        try {
            dtoType.getConstructor(Location.class);
            throw new AssertionError("target DTO must not gain a non-existent Location constructor");
        } catch (NoSuchMethodException expected) {}
        Location business = (Location)dto;
        business.setLatitude(22.3); business.setLongitude(114.2); business.setTime(987654);
        business.setBearing(17); business.setSpeed(4); business.setMock(true);
        Bundle liveExtras = new Bundle(); liveExtras.putString("origin", "live"); business.setExtras(liveExtras);
        dtoType.getMethod("setServiceType", ServiceType.class).invoke(dto, ServiceType.SYSTEM);
        dtoType.getMethod("setSuccess", boolean.class).invoke(dto, false);
        dtoType.getMethod("setFromMock", boolean.class).invoke(dto, true);
        dtoType.getMethod("setOffset", boolean.class).invoke(dto, true);
        dtoType.getMethod("setErrorCode", int.class).invoke(dto, 7);
        dtoType.getMethod("setErrorInfo", String.class).invoke(dto, "live-status");
        dtoType.getMethod("setLocationDetail", String.class).invoke(dto, "live-location-detail");
        dtoType.getMethod("setLocationType", int.class).invoke(dto, 8);
        dtoType.getMethod("setTrustedLevel", int.class).invoke(dto, 9);
        dtoType.getMethod("setCoordType", String.class).invoke(dto, "live-coordinates");
        dtoType.getMethod("setConScenario", int.class).invoke(dto, 10);
        LocationTransfer.apply(dto, saved, false);
        check(dtoType.isInstance(dto) && dto.getClass().getClassLoader()==targetLoader, "factory overlay preserves the target-loader DTO type");
        check(business.getLatitude()==31.2 && business.getLongitude()==121.5 && business.getAltitude()==4 && business.getAccuracy()==5,
                "String-only DTO accepts saved coordinates without reconstruction");
        check("Shanghai".equals(dtoType.getMethod("getCity").invoke(dto)) && "8".equals(dtoType.getMethod("getStreetNum").invoke(dto)),
                "factory overlay still applies SDK address details");
        check(dtoType.getMethod("getServiceType").invoke(dto)==ServiceType.SYSTEM &&
                !(Boolean)dtoType.getMethod("isSuccess").invoke(dto) && (Boolean)dtoType.getMethod("isFromMock").invoke(dto),
                "factory overlay preserves business ServiceType and flags");
        check((Boolean)dtoType.getMethod("isOffset").invoke(dto) && business.isMock() &&
                business.getTime()==987654 && business.getBearing()==17 && business.getSpeed()==4 && "network".equals(business.getProvider()),
                "factory overlay preserves live source metadata");
        check(business.getExtras()==liveExtras && "live".equals(liveExtras.getString("origin")), "factory overlay retains live extras");
        check(((Integer)dtoType.getMethod("getErrorCode").invoke(dto))==7 &&
                "live-status".equals(dtoType.getMethod("getErrorInfo").invoke(dto)) &&
                ((Integer)dtoType.getMethod("getLocationType").invoke(dto))==8 &&
                ((Integer)dtoType.getMethod("getTrustedLevel").invoke(dto))==9 &&
                "live-coordinates".equals(dtoType.getMethod("getCoordType").invoke(dto)) &&
                ((Integer)dtoType.getMethod("getConScenario").invoke(dto))==10 &&
                "live-location-detail".equals(dtoType.getMethod("getLocationDetail").invoke(dto)),
                "factory overlay preserves all seven live status fields");
        check(saved.getLatitude()==31.2 && saved.getLongitude()==121.5 && saved.getErrorCode()==3 && saved.getExtras()==savedExtras,
                "factory overlay leaves snapshot and its status unchanged");
        DerivedErrorLocation diagnostic = new DerivedErrorLocation("network");
        diagnostic.setLatitude(22.3); diagnostic.setLongitude(114.2);
        diagnostic.setErrorCode(7); diagnostic.setErrorInfo("live-error");
        diagnostic.setLocationDetail("live-location-detail");
        diagnostic.setServiceType(ServiceType.SYSTEM); diagnostic.setSuccess(false);
        String errorBefore = diagnostic.getErrorInfo();
        check("live-error|live-location-detail".equals(errorBefore), "derived-error fixture exercises a detail-dependent SDK diagnostic");
        LocationTransfer.apply(diagnostic, saved, false);
        check(diagnostic.getLatitude()==31.2 && diagnostic.getLongitude()==121.5, "derived-error DTO receives snapshot coordinates");
        check(errorBefore.equals(diagnostic.getErrorInfo()) && "live-location-detail".equals(diagnostic.getLocationDetail()),
                "nonzero-error derived diagnostic remains unchanged after factory overlay");
        check(diagnostic.getErrorCode()==7 && !diagnostic.isSuccess() && diagnostic.getServiceType()==ServiceType.SYSTEM,
                "derived diagnostic retains consistent error and business state");
        System.out.println("PASS: cross-loader copies, String-only DTO overlays, live metadata, bounded jitter and input immutability");
    }
}
