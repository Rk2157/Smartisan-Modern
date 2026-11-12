package android.location;
import android.os.Bundle;
/** Minimal JVM fixture; these test classes are never packaged in the APK. */
public class Location {
    private double latitude, longitude, altitude;
    private float accuracy, bearing, speed;
    private String provider;
    private long time, elapsedRealtimeNanos;
    private boolean mock;
    private Bundle extras;
    public Location(String provider) { this.provider=provider; }
    public Location(Location other) {
        latitude=other.latitude; longitude=other.longitude; altitude=other.altitude;
        accuracy=other.accuracy; extras=other.extras;
        bearing=other.bearing; speed=other.speed; provider=other.provider;
        time=other.time; elapsedRealtimeNanos=other.elapsedRealtimeNanos; mock=other.mock;
    }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public double getAltitude() { return altitude; }
    public float getAccuracy() { return accuracy; }
    public Bundle getExtras() { return extras; }
    public String getProvider() { return provider; }
    public long getTime() { return time; }
    public long getElapsedRealtimeNanos() { return elapsedRealtimeNanos; }
    public float getBearing() { return bearing; }
    public float getSpeed() { return speed; }
    public boolean isFromMockProvider() { return mock; }
    public boolean isMock() { return mock; }
    public void setLatitude(double value) { latitude=value; }
    public void setLongitude(double value) { longitude=value; }
    public void setAltitude(double value) { altitude=value; }
    public void setAccuracy(float value) { accuracy=value; }
    public void setExtras(Bundle value) { extras=value; }
    public void setProvider(String value) { provider=value; }
    public void setTime(long value) { time=value; }
    public void setElapsedRealtimeNanos(long value) { elapsedRealtimeNanos=value; }
    public void setBearing(float value) { bearing=value; }
    public void setSpeed(float value) { speed=value; }
    public void setMock(boolean value) { mock=value; }
}
