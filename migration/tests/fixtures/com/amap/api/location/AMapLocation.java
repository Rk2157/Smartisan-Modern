package com.amap.api.location;
public class AMapLocation extends android.location.Location {
    private String city;
    private String number;
    public AMapLocation() { super("gps"); }
    public AMapLocation(android.location.Location source) { super(source); }
    public String getCity() { return city; }
    public void setCity(String value) { city=value; }
    public String getStreetNum() { return number; }
    public void setNumber(String value) { number=value; }
}
