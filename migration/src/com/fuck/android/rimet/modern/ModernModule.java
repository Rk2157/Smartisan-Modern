package com.fuck.android.rimet.modern;

import android.content.SharedPreferences;
import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.Set;
import io.github.libxposed.api.XposedModule;

public final class ModernModule extends XposedModule {
    private final Set<Method> installed = new HashSet<>();
    private SharedPreferences preferences;
    private String process;

    @Override public void onModuleLoaded(ModuleLoadedParam param) {
        process = param.getProcessName();
        ModuleLog.sink = (level, message, error) -> log(level, "Smartisan102", message, error);
        ModuleLog.info("API 102 module loaded: " + process);
        // Remote preferences can be unavailable temporarily. The hook retries on the next call.
        try { preferences = getRemotePreferences(ProfileStorage.GROUP); }
        catch (RuntimeException error) { ModuleLog.error("Remote preferences not ready", error); }
    }

    @Override public void onPackageReady(PackageReadyParam param) {
        if ("com.fuck.android.rimet".equals(param.getPackageName())) return;
        ClassLoader loader = param.getClassLoader();
        Class<?> client;
        Class<?> listener;
        try {
            client = Class.forName("com.amap.api.location.AMapLocationClient", false, loader);
            listener = Class.forName("com.amap.api.location.AMapLocationListener", false, loader);
        } catch (ClassNotFoundException absent) {
            ModuleLog.info("AMap SDK not present: " + param.getPackageName());
            return;
        }
        ModuleLog.info("LoadPackage: pkg=" + param.getPackageName() + " proc=" + process);
        install(client, "getLastKnownLocation", new Class<?>[0], chain -> {
            Object location = ProfileStorage.value(readProfile(), "c");
            if (location == null) return chain.proceed();
            return LocationTransfer.copy(((Method) chain.getExecutable()).getReturnType(), location, null, false);
        });
        install(client, "setLocationListener", new Class<?>[]{listener}, chain -> {
            Object callback = chain.getArg(0);
            if (callback != null) {
                try {
                    Class<?> locationType = Class.forName("com.amap.api.location.AMapLocation", false, loader);
                    install(callback.getClass(), "onLocationChanged", new Class<?>[]{locationType}, event -> {
                        Object[] args = event.getArgs().toArray();
                        Object location = ProfileStorage.value(readProfile(), "c");
                        if (location != null && args[0] != null) {
                            Class<?> accepted = ((Method) event.getExecutable()).getParameterTypes()[0];
                            args[0] = LocationTransfer.copy(accepted, location, args[0], true);
                        }
                        return event.proceed(args);
                    });
                } catch (ReflectiveOperationException error) {
                    ModuleLog.error("Cannot install location callback", error);
                }
            }
            // Keep the original listener identity so removal and re-registration still work.
            return chain.proceed();
        });
        try {
            Class<?> wifi = Class.forName("android.net.wifi.WifiManager", false, loader);
            installProfileValue(wifi, "isWifiEnabled", "d", "getWifiEnabled");
            installProfileValue(wifi, "getScanResults", "d", "getScanResults");
            installProfileValue(wifi, "getConnectionInfo", "d", "getConnectionInfo");
            Class<?> telephony = Class.forName("android.telephony.TelephonyManager", false, loader);
            installProfileValue(telephony, "getAllCellInfo", "a", "getCellInfoList");
        } catch (ClassNotFoundException error) { ModuleLog.error("Android service class unavailable", error); }
    }

    private synchronized Object readProfile() {
        try {
            if (preferences == null) preferences = getRemotePreferences(ProfileStorage.GROUP);
            // Decode a fresh copy: Android Location / WifiInfo / Lists are mutable.
            return ProfileStorage.decode(preferences.getString(ProfileStorage.PAYLOAD, null));
        } catch (Exception error) {
            preferences = null;
            ModuleLog.error("Cannot read remote snapshot; reopen module and reselect it", error);
            return null;
        }
    }

    private void installProfileValue(Class<?> owner, String method, String part, String getter) {
        install(owner, method, new Class<?>[0], chain -> {
            Object detail = ProfileStorage.value(readProfile(), part);
            if (detail == null) return chain.proceed();
            return ProfileStorage.value(detail, getter);
        });
    }

    private synchronized void install(Class<?> owner, String name, Class<?>[] args, Hooker hooker) {
        try {
            Method method = owner.getMethod(name, args);
            if (installed.contains(method)) return;
            hook(method).setExceptionMode(ExceptionMode.PROTECTIVE).intercept(hooker);
            installed.add(method);
            ModuleLog.info("Hook installed: " + method.getDeclaringClass().getName() + "#" + name);
        } catch (Exception | LinkageError error) {
            ModuleLog.error("Hook unavailable: " + owner.getName() + "#" + name, error);
        }
    }

    // API 102 hot reload is deliberately not opted in: listeners already held by the target app
    // need a process restart. The framework's default onHotReloading() returns false.
}
