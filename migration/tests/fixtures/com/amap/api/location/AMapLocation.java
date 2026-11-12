package com.amap.api.location;
public class AMapLocation extends android.location.Location {
    private String city;
    private String number;
    private String address;
    private String errorInfo;
    private String locationDetail;
    private int errorCode, locationType;
    private int trustedLevel, conScenario;
    private String coordType;
    private boolean offset;
    public AMapLocation() { super("gps"); }
    public AMapLocation(String provider) { super(provider); }
    public AMapLocation(android.location.Location source) {
        super(source);
        if (source instanceof AMapLocation) {
            AMapLocation amap = (AMapLocation) source;
            city=amap.city; number=amap.number; address=amap.address;
            errorCode=amap.errorCode; errorInfo=amap.errorInfo;
            locationDetail=amap.locationDetail;
            locationType=amap.locationType; offset=amap.offset;
            trustedLevel=amap.trustedLevel; conScenario=amap.conScenario; coordType=amap.coordType;
        }
    }
    public String getCity() { return city; }
    public void setCity(String value) { city=value; }
    public String getStreetNum() { return number; }
    public void setNumber(String value) { number=value; }
    public String getAddress() { return address; }
    public void setAddress(String value) { address=value; }
    public int getErrorCode() { return errorCode; }
    public void setErrorCode(int value) { errorCode=value; }
    public String getErrorInfo() { return errorInfo; }
    public void setErrorInfo(String value) { errorInfo=value; }
    public String getLocationDetail() { return locationDetail; }
    public void setLocationDetail(String value) { locationDetail=value; }
    public int getLocationType() { return locationType; }
    public void setLocationType(int value) { locationType=value; }
    public boolean isOffset() { return offset; }
    public void setOffset(boolean value) { offset=value; }
    public int getTrustedLevel() { return trustedLevel; }
    public void setTrustedLevel(int value) { trustedLevel=value; }
    public int getConScenario() { return conScenario; }
    public void setConScenario(int value) { conScenario=value; }
    public String getCoordType() { return coordType; }
    public void setCoordType(String value) { coordType=value; }
}
