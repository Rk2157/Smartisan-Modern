import android.content.SharedPreferences;
import android.location.Location;
import android.os.Bundle;
import com.alibaba.android.rimet.LocationService.ServiceType;
import com.alibaba.android.rimet.model.DtLocation;
import com.amap.api.location.*;
import com.fuck.android.rimet.modern.ModernModule;
import com.fuck.android.rimet.profile.Profile;
import io.github.libxposed.api.*;
import java.lang.reflect.*;
import java.util.*;

/** JVM contract tests with the real API 102 classes and a fake framework (no ART/Binder). */
public final class ModernModuleTest {
    static int assertions;
    static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    @SuppressWarnings("unchecked")
    static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return (T) Proxy.newProxyInstance(ModernModuleTest.class.getClassLoader(), new Class<?>[]{type}, handler);
    }
    public static class ParentListener implements AMapLocationListener {
        public void onLocationChanged(AMapLocation location) {}
    }
    public static final class ChildListener extends ParentListener {}

    interface OriginalCall { Object call(Object[] arguments) throws Throwable; }
    static final class Invocation {
        Object result;
        Object original;
        Object[] arguments;
        int calls;
        double originalLatitude, originalLongitude;
    }

    static final class FakeFramework {
        final Map<Method, XposedInterface.Hooker> hooks = new LinkedHashMap<>();
        final Set<Method> protective = new HashSet<>();
        int reads;
        int failures;
        String payload;
        String reject;
        Invocation lastCall;
        final SharedPreferences preferences = proxy(SharedPreferences.class, (p, method, args) -> {
            if (method.getName().equals("getString")) { reads++; return payload; }
            throw new AssertionError(method);
        });
        final XposedInterface api = proxy(XposedInterface.class, (p, method, args) -> {
            switch (method.getName()) {
                case "log": return null;
                case "getRemotePreferences":
                    if (failures-- > 0) throw new IllegalStateException("Temporary binder failure");
                    return preferences;
                case "hook":
                    Method target = (Method) args[0];
                    if (target.getName().equals(reject)) throw new IllegalStateException("Not hookable");
                    return proxy(XposedInterface.HookBuilder.class, (b, op, values) -> {
                        if (op.getName().equals("setExceptionMode")) {
                            check(values[0] == XposedInterface.ExceptionMode.PROTECTIVE, "protective hooks");
                            protective.add(target);
                            return b;
                        }
                        if (op.getName().equals("intercept")) {
                            check(!hooks.containsKey(target), "duplicate registration");
                            hooks.put(target, (XposedInterface.Hooker) values[0]);
                            return null;
                        }
                        throw new AssertionError(op);
                    });
                default: throw new AssertionError(method);
            }
        });
        ModernModule module() {
            ModernModule module = new ModernModule();
            // Framework-only attachment is invoked only by this test framework.
            module.attachFramework(api, () -> {});
            module.onModuleLoaded(proxy(XposedModuleInterface.ModuleLoadedParam.class,
                    (p, method, args) -> method.getName().equals("getProcessName") ? "test.target" : false));
            return module;
        }
        XposedModuleInterface.PackageReadyParam ready(String packageName) {
            return ready(packageName, ModernModuleTest.class.getClassLoader());
        }
        XposedModuleInterface.PackageReadyParam ready(String packageName, ClassLoader loader) {
            return proxy(XposedModuleInterface.PackageReadyParam.class, (p, method, args) -> {
                switch (method.getName()) {
                    case "getPackageName": return packageName;
                    case "getClassLoader": return loader;
                    default: throw new AssertionError(method);
                }
            });
        }
        Method method(String name) {
            return hooks.keySet().stream().filter(m -> m.getName().equals(name)).findFirst().orElseThrow();
        }
        Invocation invoke(String name, Object... arguments) throws Throwable {
            Method target = method(name);
            return invokeOriginal(target, values -> {
                try { return target.invoke(null, values); }
                catch (InvocationTargetException error) { throw error.getCause(); }
            }, arguments);
        }
        Invocation invokeOriginal(Method target, OriginalCall original, Object... values) throws Throwable {
            Invocation call = new Invocation();
            lastCall = call;
            call.result = hooks.get(target).intercept(proxy(XposedInterface.Chain.class, (p, method, args) -> {
                switch (method.getName()) {
                    case "getExecutable": return target;
                    case "getArg": return values[(Integer) args[0]];
                    case "getArgs": return Collections.unmodifiableList(Arrays.asList(values));
                    case "proceed":
                        call.calls++;
                        call.arguments = args != null && args.length == 1 ? (Object[]) args[0] : values;
                        call.original = original.call(call.arguments);
                        if (call.original instanceof Location) {
                            call.originalLatitude = ((Location)call.original).getLatitude();
                            call.originalLongitude = ((Location)call.original).getLongitude();
                        }
                        return call.original;
                    default: throw new AssertionError(method);
                }
            }));
            return call;
        }
        void proceedExactlyOnce(String name, Object... values) throws Throwable {
            Method target = method(name);
            int[] count = {0};
            Object token = new Object();
            Object result = hooks.get(target).intercept(proxy(XposedInterface.Chain.class, (p, method, args) -> {
                switch (method.getName()) {
                    case "getExecutable": return target;
                    case "getArg": return values[(Integer) args[0]];
                    case "getArgs": return Collections.unmodifiableList(Arrays.asList(values));
                    case "proceed":
                        count[0]++;
                        if (args != null && args.length == 1) check(Arrays.equals(values, (Object[]) args[0]), "original callback arguments preserved");
                        return token;
                    default: throw new AssertionError(method);
                }
            }));
            check(count[0] == 1 && result == token, "missing snapshot must call through once: " + name);
        }
    }

    static AMapLocation saved(double latitude, double longitude, String city) {
        AMapLocation location = new AMapLocation("saved-provider");
        location.setLatitude(latitude); location.setLongitude(longitude);
        location.setAltitude(45); location.setAccuracy(6);
        location.setCity(city); location.setAddress(city + " saved address");
        location.setNumber("81"); location.setTime(1000);
        location.setLocationType(2); location.setErrorInfo("snapshot status");
        Bundle extras = new Bundle(); extras.putString("source", "snapshot"); location.setExtras(extras);
        return location;
    }
    static void nearSaved(Location actual, Location saved, String event) {
        check(Math.abs(actual.getLatitude()-saved.getLatitude()) < 0.000046, event + " latitude uses selected snapshot");
        double bound = 0.000046 / Math.cos(Math.toRadians(saved.getLatitude()));
        check(Math.abs(actual.getLongitude()-saved.getLongitude()) < bound, event + " longitude jitter is bounded");
        check(actual.getAltitude()==saved.getAltitude() && actual.getAccuracy()==saved.getAccuracy(), event + " altitude and accuracy use snapshot");
    }
    static void dingTalkFactories() throws Throwable {
        FakeFramework framework = new FakeFramework();
        ModernModule module = framework.module();
        module.onPackageReady(framework.ready("com.alibaba.android.rimet"));
        check(framework.hooks.size()==8, "DingTalk adds both conversion boundaries before any listener registration");
        check(framework.method("fromLocation").getDeclaringClass()==DtLocation.class, "SYSTEM converter hooked");
        check(framework.method("fromAMapLocation").getDeclaringClass()==DtLocation.class, "GAODE converter hooked");
        module.onPackageReady(framework.ready("com.alibaba.android.rimet"));
        check(framework.hooks.size()==8, "DingTalk factory hooks are idempotent");

        AMapLocation first = saved(31.2, 121.5, "Shanghai");
        framework.payload = Profile.encode("first", first);
        Location raw = new Location("network");
        raw.setLatitude(22.3); raw.setLongitude(114.2);
        raw.setAltitude(10); raw.setAccuracy(80); raw.setMock(true);
        raw.setTime(987654); raw.setElapsedRealtimeNanos(123456789);
        raw.setBearing(17); raw.setSpeed(4);
        Bundle liveExtras = new Bundle(); liveExtras.putString("source", "system"); raw.setExtras(liveExtras);
        Invocation system = framework.invoke("fromLocation", raw, ServiceType.SYSTEM);
        DtLocation systemResult = (DtLocation)system.result;
        check(system.calls==1 && system.result==system.original, "SYSTEM preserves the original DTO and calls converter once");
        check(Math.abs(system.originalLatitude-22.303)<1e-10 && Math.abs(system.originalLongitude-114.204)<1e-10, "SYSTEM conversion executes before snapshot override");
        nearSaved(systemResult, first, "first SYSTEM result");
        check(systemResult.getServiceType()==ServiceType.SYSTEM, "SYSTEM business ServiceType retained");
        check(systemResult.isSuccess() && systemResult.isFromMock() && systemResult.isMock(), "SYSTEM DTO success and mock flags retained");
        check("network".equals(systemResult.getProvider()) && systemResult.getTime()==987654, "SYSTEM source and fresh timestamp retained");
        check(systemResult.getBearing()==17 && systemResult.getSpeed()==4, "SYSTEM motion metadata retained");
        check(systemResult.getExtras()==liveExtras && "system".equals(liveExtras.getString("source")), "SYSTEM factory extras retained instead of stale snapshot extras");
        check("Shanghai".equals(systemResult.getCity()) && first.getAddress().equals(systemResult.getAddress()), "SYSTEM receives snapshot address");
        check(raw.getLatitude()==22.3 && raw.getLongitude()==114.2 && raw.getAccuracy()==80 && raw.isMock(), "raw Android Location remains unchanged");
        check(first.getLatitude()==31.2 && first.getLongitude()==121.5 && "Shanghai".equals(first.getCity()), "selected snapshot remains unchanged");

        AMapLocation second = saved(48.85, 2.35, "Paris");
        framework.payload = Profile.encode("second", second);
        AMapLocation incoming = new AMapLocation("amap-provider");
        incoming.setLatitude(23.1); incoming.setLongitude(113.2);
        incoming.setAccuracy(90); incoming.setCity("real-city");
        incoming.setAddress("real-address"); incoming.setTime(654321);
        incoming.setOffset(true); incoming.setLocationType(8);
        incoming.setErrorCode(7); incoming.setErrorInfo("live failure");
        Bundle gaodeExtras = new Bundle(); gaodeExtras.putString("source", "gaode"); incoming.setExtras(gaodeExtras);
        Invocation gaode = framework.invoke("fromAMapLocation", incoming, ServiceType.GAODE);
        DtLocation gaodeResult = (DtLocation)gaode.result;
        nearSaved(gaodeResult, second, "refreshed GAODE result");
        check(gaode.calls==1 && gaode.result==gaode.original, "GAODE retains exact factory DTO without replacing its type");
        check(gaodeResult.getServiceType()==ServiceType.GAODE && !gaodeResult.isSuccess(), "GAODE business metadata retained");
        check(!gaodeResult.isFromMock() && !gaodeResult.isMock() && gaodeResult.isOffset(), "GAODE false mock and true offset flags retained");
        check(gaodeResult.getErrorCode()==7 && "live failure".equals(gaodeResult.getErrorInfo()) && gaodeResult.getLocationType()==8,
                "GAODE live error and location status remain consistent with business flags");
        check(gaodeResult.getExtras()==gaodeExtras && "gaode".equals(gaodeExtras.getString("source")), "GAODE live extras retained");
        check(gaodeResult.getTime()==654321 && "amap-provider".equals(gaodeResult.getProvider()), "GAODE source timestamp and provider retained");
        check("Paris".equals(gaodeResult.getCity()) && second.getAddress().equals(gaodeResult.getAddress()), "fresh selection used on the next event");
        check(incoming.getLatitude()==23.1 && incoming.getLongitude()==113.2 && "real-city".equals(incoming.getCity()), "original GAODE input remains unchanged");

        Invocation cached = framework.invokeOriginal(framework.method("getLastKnownLocation"), arguments -> incoming);
        check(cached.calls==0 && cached.result instanceof AMapLocation, "SDK cached getter uses selected snapshot without original lookup");
        Location cachedResult = (Location)cached.result;
        check(cachedResult.getLatitude()==48.85 && cachedResult.getLongitude()==2.35, "cached getter matches current snapshot without jitter");

        int reads = framework.reads;
        Invocation empty = framework.invoke("fromLocation", null, ServiceType.SYSTEM);
        check(empty.calls==1 && empty.result==null && framework.reads==reads, "null factory result remains null without snapshot access");

        framework.payload = null;
        Invocation missing = framework.invoke("fromLocation", raw, ServiceType.SYSTEM);
        check(missing.calls==1 && missing.result==missing.original, "missing snapshot keeps original result and calls converter once");
        check(Math.abs(((Location)missing.result).getLatitude()-22.303)<1e-10, "missing snapshot retains SYSTEM conversion");
        framework.proceedExactlyOnce("getLastKnownLocation");

        framework.payload = "not base64!";
        Invocation unreadable = framework.invoke("fromAMapLocation", incoming, ServiceType.GAODE);
        check(unreadable.calls==1 && unreadable.result==unreadable.original && ((Location)unreadable.result).getLatitude()==23.1,
                "snapshot decode failure retains original result exactly once");
        framework.payload = Profile.encode("recovered", first);
        nearSaved((Location)framework.invoke("fromLocation", raw, ServiceType.SYSTEM).result, first, "snapshot recovers after read failure");

        framework.payload = Profile.encodeRaw("invalid-location", new Object());
        Invocation applyFailure = framework.invoke("fromLocation", raw, ServiceType.SYSTEM);
        check(applyFailure.calls==1 && applyFailure.result==applyFailure.original,
                "snapshot application exception never reruns the original converter");
        check(Math.abs(((Location)applyFailure.result).getLatitude()-22.303)<1e-10, "snapshot application failure keeps original coordinates");

        IllegalStateException originalFailure = new IllegalStateException("converter failed");
        try {
            framework.invokeOriginal(framework.method("fromLocation"), arguments -> { throw originalFailure; }, raw, ServiceType.SYSTEM);
            throw new AssertionError("original converter failure must propagate");
        } catch (IllegalStateException error) {
            check(error==originalFailure && framework.lastCall.calls==1, "original converter exception propagates without a second invocation");
        }

        FakeFramework withoutClient = new FakeFramework();
        ModernModule partial = withoutClient.module();
        ClassLoader loader = new ClassLoader(ModernModuleTest.class.getClassLoader()) {
            @Override protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                if (name.equals("com.amap.api.location.AMapLocationClient") || name.equals("com.amap.api.location.AMapLocationListener"))
                    throw new ClassNotFoundException(name);
                return super.loadClass(name, resolve);
            }
        };
        partial.onPackageReady(withoutClient.ready("com.alibaba.android.rimet", loader));
        check(withoutClient.hooks.size()==2, "DingTalk conversion hooks survive absent SDK client/listener classes");
        FakeFramework oneFactory = new FakeFramework();
        oneFactory.reject="fromLocation";
        ModernModule single = oneFactory.module();
        single.onPackageReady(oneFactory.ready("com.alibaba.android.rimet"));
        check(oneFactory.hooks.containsKey(DtLocation.class.getMethod("fromAMapLocation", AMapLocation.class, ServiceType.class)),
                "one converter hook failure does not prevent the other converter");
    }

    public static void main(String[] args) throws Throwable {
        FakeFramework framework = new FakeFramework();
        ModernModule module = framework.module();
        module.onPackageReady(framework.ready("com.fuck.android.rimet"));
        check(framework.hooks.isEmpty(), "module app must not hook itself");
        module.onPackageReady(framework.ready("test.target"));
        check(framework.hooks.size() == 6, "six original hooks registered");
        module.onPackageReady(framework.ready("test.target"));
        check(framework.hooks.size() == 6, "package re-entry is idempotent");
        for (String name : List.of("getLastKnownLocation", "isWifiEnabled", "getScanResults", "getConnectionInfo", "getAllCellInfo"))
            framework.proceedExactlyOnce(name);
        framework.proceedExactlyOnce("setLocationListener", (Object) null);
        check(framework.hooks.size() == 6, "null listener does not install a callback");
        framework.proceedExactlyOnce("setLocationListener", new ChildListener());
        check(framework.hooks.size() == 7, "inherited callback installed");
        framework.proceedExactlyOnce("setLocationListener", new ChildListener());
        check(framework.hooks.size() == 7, "callback hook deduplicated");
        framework.proceedExactlyOnce("onLocationChanged", new AMapLocation());
        check(framework.reads == 6, "preferences read on each event (no stale lazy cache)");
        check(!module.onHotReloading(null), "unsafe hot reload is declined");
        FakeFramework degraded = new FakeFramework();
        degraded.failures = 1;
        degraded.reject = "getLastKnownLocation";
        ModernModule second = degraded.module();
        second.onPackageReady(degraded.ready("test.target"));
        check(degraded.hooks.size() == 5, "one hook failure does not prevent independent hooks");
        degraded.proceedExactlyOnce("isWifiEnabled");
        check(degraded.reads == 1, "remote preferences retried after initial binder failure");
        dingTalkFactories();
        System.out.println("PASS: " + assertions + " API 102 contract assertions");
    }
}
