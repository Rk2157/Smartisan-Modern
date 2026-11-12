package com.alibaba.android.rimet;

/** Names and identity match the target app; no location service is run in JVM tests. */
public final class LocationService {
    public enum ServiceType {
        SYSTEM, GAODE, GOOGLE, HUAWEI, WIFI, SYSTEM_GPS, SYSTEM_NETWORK, SYSTEM_FUSED
    }
}
