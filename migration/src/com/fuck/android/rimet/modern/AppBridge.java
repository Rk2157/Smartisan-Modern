package com.fuck.android.rimet.modern;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import io.github.libxposed.service.XposedService;
import io.github.libxposed.service.XposedServiceHelper;

/** App-side service code. This class never links against the compile-only module API. */
public final class AppBridge {
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static volatile Context context;
    private static volatile XposedService service;
    private static boolean initialized;

    public static synchronized void init(Context app) {
        if (initialized) return;
        initialized = true;
        context = app.getApplicationContext();
        XposedServiceHelper.registerListener(new XposedServiceHelper.OnServiceListener() {
            @Override public void onServiceBind(XposedService bound) {
                try {
                    if (bound.getApiVersion() < 102) {
                        ModuleLog.info("Framework service is older than API 102");
                        return;
                    }
                    service = bound;
                    ModuleLog.info("Service connected: " + bound.getFrameworkName() + " API " + bound.getApiVersion());
                    sync();
                } catch (RuntimeException error) {
                    ModuleLog.error("Cannot connect to framework service", error);
                }
            }
            @Override public void onServiceDied(XposedService dead) {
                if (service == dead) service = null;
                ModuleLog.info("Framework service disconnected");
            }
        });
    }

    public static boolean isActive() {
        XposedService current = service;
        if (current == null) return false;
        try { return current.getApiVersion() >= 102; }
        catch (RuntimeException error) {
            if (service == current) service = null;
            return false;
        }
    }

    public static void sync() {
        if (context == null || service == null) return; // Replayed when the framework binds.
        WORKER.execute(() -> {
            Context app = context;
            XposedService current = service;
            if (app == null || current == null) return;
            try {
                SharedPreferences local = app.getSharedPreferences(ProfileStorage.GROUP, Context.MODE_PRIVATE);
                // Read a coherent pair even if the UI selects another snapshot concurrently.
                java.util.Map<String, ?> values = local.getAll();
                String payload = (String) values.get(ProfileStorage.PAYLOAD);
                String id = (String) values.get(ProfileStorage.ID);
                if (payload != null && payload.length() > ProfileStorage.MAX_ENCODED_SIZE)
                    throw new IllegalArgumentException("Snapshot is too large");
                SharedPreferences.Editor editor = current.getRemotePreferences(ProfileStorage.GROUP).edit();
                if (payload == null || id == null) editor.remove(ProfileStorage.PAYLOAD).remove(ProfileStorage.ID);
                else editor.putString(ProfileStorage.PAYLOAD, payload).putString(ProfileStorage.ID, id);
                if (!editor.commit()) throw new IllegalStateException("Framework rejected snapshot sync");
                ModuleLog.info(payload == null ? "Remote snapshot cleared" : "Remote snapshot synchronized");
            } catch (RuntimeException error) {
                ModuleLog.error("Snapshot sync failed; reopen the module app and select the snapshot again", error);
                new Handler(Looper.getMainLooper()).post(() -> Toast.makeText(app,
                        "快照同步失败，请检查框架后重新打开模块并选择快照", Toast.LENGTH_LONG).show());
            }
        });
    }
}
