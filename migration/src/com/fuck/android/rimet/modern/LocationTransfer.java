package com.fuck.android.rimet.modern;

import android.location.Location;
import java.lang.reflect.Method;
import java.util.concurrent.ThreadLocalRandom;

/** Copies into the target app's AMap class, avoiding cross-classloader return-type failures. */
public final class LocationTransfer {
    private static final String[] DETAILS = {
        "District", "LocationDetail", "LocationType", "PoiName", "Country", "BuildingId",
        "AdCode", "Description", "CityCode", "Street", "Province", "TrustedLevel", "Floor",
        "Address", "ErrorCode", "ErrorInfo", "CoordType", "City", "Road", "ConScenario", "AoiName"
    };

    public static Object copy(Class<?> targetType, Object snapshot, Object original, boolean jitter)
            throws ReflectiveOperationException {
        Location source = (Location) snapshot;
        Location base = original instanceof Location ? (Location) original : source;
        Object target = targetType.getConstructor(Location.class).newInstance(base);
        ((Location) target).setExtras(source.getExtras());
        applySnapshot(target, snapshot, jitter, false);
        return target;
    }

    /** Updates coordinates/address while retaining the target model's extras and status/source fields. */
    public static void apply(Object target, Object snapshot, boolean jitter)
            throws ReflectiveOperationException {
        applySnapshot(target, snapshot, jitter, true);
    }

    private static void applySnapshot(Object target, Object snapshot, boolean jitter, boolean preserveStatus)
            throws ReflectiveOperationException {
        Location source = (Location) snapshot;
        Location location = (Location) target;
        location.setLatitude(source.getLatitude());
        location.setLongitude(source.getLongitude());
        location.setAltitude(source.getAltitude());
        location.setAccuracy(source.getAccuracy());
        if (jitter) {
            // Independent offsets around the saved coordinate; never mutate the saved snapshot.
            double latitude = source.getLatitude();
            double angle = 5.0 / 6371000.0;
            double cosine = Math.cos(Math.toRadians(latitude));
            double longitudeAngle = Math.asin(Math.min(1.0, angle / Math.max(1e-8, Math.abs(cosine))));
            location.setLatitude(Math.max(-90.0, Math.min(90.0,
                    latitude + Math.toDegrees(angle * ThreadLocalRandom.current().nextDouble(-1.0, 1.0)))));
            double lon = source.getLongitude() + Math.toDegrees(longitudeAngle * ThreadLocalRandom.current().nextDouble(-1.0, 1.0));
            location.setLongitude((lon + 540.0) % 360.0 - 180.0);
        }
        for (String detail : DETAILS) {
            if (preserveStatus && isStatusDetail(detail)) continue;
            copyDetail(snapshot, target, "get" + detail, "set" + detail);
        }
        copyDetail(snapshot, target, "getStreetNum", "setNumber");
    }

    private static boolean isStatusDetail(String detail) {
        // SDK error messages can derive their text from LocationDetail; retain it with status.
        return "LocationDetail".equals(detail) || "LocationType".equals(detail) || "TrustedLevel".equals(detail)
                || "ErrorCode".equals(detail) || "ErrorInfo".equals(detail)
                || "CoordType".equals(detail) || "ConScenario".equals(detail);
    }

    private static void copyDetail(Object source, Object target, String getter, String setter)
            throws ReflectiveOperationException {
        try {
            Method read = source.getClass().getMethod(getter);
            Method write = target.getClass().getMethod(setter, read.getReturnType());
            write.invoke(target, read.invoke(source));
        } catch (NoSuchMethodException ignored) {
            // AMap SDK releases expose different optional address fields.
        }
    }
}
