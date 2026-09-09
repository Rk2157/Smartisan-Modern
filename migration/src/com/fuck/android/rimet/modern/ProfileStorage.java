package com.fuck.android.rimet.modern;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Parcel;
import android.os.Parcelable;
import android.util.Base64;
import java.lang.reflect.InvocationTargetException;

/** Keeps the existing Parcel snapshot format and private local preferences. */
public final class ProfileStorage {
    public static final String GROUP = "profile";
    public static final String PAYLOAD = "sp";
    public static final String ID = "spid";
    public static final int MAX_ENCODED_SIZE = 384 * 1024;

    public static Object value(Object receiver, String method) throws ReflectiveOperationException {
        if (receiver == null) return null;
        return receiver.getClass().getMethod(method).invoke(receiver);
    }

    public static Object decode(String encoded) throws ReflectiveOperationException {
        if (encoded == null || encoded.isEmpty()) return null;
        if (encoded.length() > MAX_ENCODED_SIZE) throw new IllegalArgumentException("Snapshot is too large");
        byte[] bytes = Base64.decode(encoded, Base64.NO_WRAP);
        Parcel parcel = Parcel.obtain();
        try {
            parcel.unmarshall(bytes, 0, bytes.length);
            parcel.setDataPosition(0);
            Class<?> type = Class.forName("com.fuck.android.rimet.profile.Profile", true,
                    ProfileStorage.class.getClassLoader());
            Parcelable.Creator<?> creator = (Parcelable.Creator<?>) type.getField("CREATOR").get(null);
            return creator.createFromParcel(parcel);
        } finally {
            parcel.recycle();
        }
    }

    public static Object readLocal(Context context) {
        if (context == null) return null;
        try {
            return decode(context.getSharedPreferences(GROUP, Context.MODE_PRIVATE).getString(PAYLOAD, null));
        } catch (Exception error) {
            ModuleLog.error("Cannot read local snapshot; recreate it on this Android version", error);
            return null;
        }
    }

    public static boolean select(Context context, Object profile) {
        if (context == null) return false;
        try {
            SharedPreferences.Editor editor = context.getSharedPreferences(GROUP, Context.MODE_PRIVATE).edit();
            if (profile == null) {
                editor.remove(ID).remove(PAYLOAD);
            } else {
                Parcel parcel = Parcel.obtain();
                String encoded;
                try {
                    ((Parcelable) profile).writeToParcel(parcel, 0);
                    encoded = Base64.encodeToString(parcel.marshall(), Base64.NO_WRAP);
                } finally {
                    parcel.recycle();
                }
                if (encoded.length() > MAX_ENCODED_SIZE) throw new IllegalArgumentException("Snapshot is too large");
                editor.putString(ID, (String) value(profile, "b")).putString(PAYLOAD, encoded);
            }
            if (!editor.commit()) return false;
            AppBridge.sync();
            context.getContentResolver().notifyChange(Uri.parse("content://com.fuck.android.rimet.provider/profiles"), null);
            return true;
        } catch (Exception error) {
            ModuleLog.error("Cannot save selected snapshot", error);
            return false;
        }
    }
}
