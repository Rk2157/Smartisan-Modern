package android.location;
import android.os.Bundle;
/** Minimal JVM fixture; these test classes are never packaged in the APK. */
public class Location {
    private double latitude, longitude, altitude;
    private float accuracy;
    private Bundle extras;
    public Location(String provider) {}
    public Location(Location other) {
        latitude=other.latitude; longitude=other.longitude; altitude=other.altitude;
        accuracy=other.accuracy; extras=other.extras;
    }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public double getAltitude() { return altitude; }
    public float getAccuracy() { return accuracy; }
    public Bundle getExtras() { return extras; }
    public void setLatitude(double value) { latitude=value; }
    public void setLongitude(double value) { longitude=value; }
    public void setAltitude(double value) { altitude=value; }
    public void setAccuracy(float value) { accuracy=value; }
    public void setExtras(Bundle value) { extras=value; }
}
