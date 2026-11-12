package com.fuck.android.rimet.profile;

import android.os.Parcel;
import android.os.Parcelable;
import android.util.Base64;
import com.amap.api.location.AMapLocation;
import java.util.HashMap;
import java.util.Map;

/** Test snapshots selected by token; each decode returns a fresh mutable location. */
public final class Profile implements Parcelable {
    private static final Map<String, Object> SAVED = new HashMap<>();
    private final Object location;
    private final String token;

    private Profile(String token, Object location) {
        this.token=token;
        this.location=location;
    }
    public static String encode(String token, AMapLocation location) {
        return encodeRaw(token, new AMapLocation(location));
    }
    public static String encodeRaw(String token, Object location) {
        SAVED.put(token, location);
        return Base64.encodeToString(token.getBytes(java.nio.charset.StandardCharsets.UTF_8), Base64.NO_WRAP);
    }
    public Object c() { return location; }
    public Object a() { return null; }
    public Object d() { return null; }
    public String b() { return token; }
    @Override public int describeContents() { return 0; }
    @Override public void writeToParcel(Parcel destination, int flags) { destination.writeString(token); }
    public static final Parcelable.Creator<Profile> CREATOR = new Parcelable.Creator<Profile>() {
        @Override public Profile createFromParcel(Parcel source) {
            String token = source.readString();
            Object location = SAVED.get(token);
            if (location == null) throw new IllegalArgumentException("Unknown test snapshot");
            return new Profile(token, location instanceof AMapLocation ? new AMapLocation((AMapLocation) location) : location);
        }
        @Override public Profile[] newArray(int size) { return new Profile[size]; }
    };
}
