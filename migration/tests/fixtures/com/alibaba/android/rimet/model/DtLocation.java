package com.alibaba.android.rimet.model;

import android.location.Location;
import com.alibaba.android.rimet.LocationService.ServiceType;
import com.amap.api.location.AMapLocation;

/** Target-app contract: the DTO has only a String constructor, not Location/zero-arg. */
public class DtLocation extends AMapLocation {
    private ServiceType serviceType;
    private boolean success, fromMock;

    public DtLocation(String provider) { super(provider); }

    public static DtLocation fromLocation(Location source, ServiceType type) {
        if (source == null) return null;
        DtLocation result = new DtLocation(source.getProvider());
        copyLocation(source, result);
        // A visible synthetic datum conversion lets tests distinguish before/after-original hooks.
        result.setLatitude(source.getLatitude() + 0.003);
        result.setLongitude(source.getLongitude() + 0.004);
        result.setFromMock(source.isFromMockProvider());
        result.setMock(source.isFromMockProvider());
        result.setServiceType(type);
        result.setSuccess(true);
        return result;
    }

    public static DtLocation fromAMapLocation(AMapLocation source, ServiceType type) {
        if (source == null) return null;
        DtLocation result = new DtLocation(source.getProvider());
        copyLocation(source, result);
        result.setCity(source.getCity());
        result.setAddress(source.getAddress());
        result.setNumber(source.getStreetNum());
        result.setLocationType(source.getLocationType());
        result.setErrorCode(source.getErrorCode());
        result.setErrorInfo(source.getErrorInfo());
        result.setLocationDetail(source.getLocationDetail());
        result.setOffset(source.isOffset());
        result.setTrustedLevel(source.getTrustedLevel());
        result.setConScenario(source.getConScenario());
        result.setCoordType(source.getCoordType());
        result.setMock(source.isMock());
        result.setFromMock(source.isFromMockProvider());
        result.setServiceType(type);
        result.setSuccess(source.getErrorCode() == 0);
        return result;
    }

    private static void copyLocation(Location source, DtLocation target) {
        target.setLatitude(source.getLatitude());
        target.setLongitude(source.getLongitude());
        target.setAltitude(source.getAltitude());
        target.setAccuracy(source.getAccuracy());
        target.setTime(source.getTime());
        target.setElapsedRealtimeNanos(source.getElapsedRealtimeNanos());
        target.setBearing(source.getBearing());
        target.setSpeed(source.getSpeed());
        target.setExtras(source.getExtras());
    }

    public ServiceType getServiceType() { return serviceType; }
    public void setServiceType(ServiceType value) { serviceType=value; }
    public boolean isSuccess() { return success; }
    public void setSuccess(boolean value) { success=value; }
    public boolean isFromMock() { return fromMock; }
    @Override public boolean isFromMockProvider() { return fromMock; }
    public void setFromMock(boolean value) { fromMock=value; }
}
