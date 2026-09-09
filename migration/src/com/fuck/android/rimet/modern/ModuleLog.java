package com.fuck.android.rimet.modern;

import android.util.Log;

public final class ModuleLog {
    public interface Sink { void write(int level, String message, Throwable error); }
    public static volatile Sink sink;
    public static void info(String message) { write(Log.INFO, message, null); }
    public static void error(String message, Throwable error) { write(Log.ERROR, message, error); }
    private static void write(int level, String message, Throwable error) {
        Sink current = sink;
        if (current != null) current.write(level, message, error);
        else if (error != null) Log.e("Smartisan102", message, error);
        else Log.println(level, "Smartisan102", message);
    }
}
