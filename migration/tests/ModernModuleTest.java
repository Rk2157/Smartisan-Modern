import android.content.SharedPreferences;
import com.amap.api.location.*;
import com.fuck.android.rimet.modern.ModernModule;
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

    static final class FakeFramework {
        final Map<Method, XposedInterface.Hooker> hooks = new LinkedHashMap<>();
        final Set<Method> protective = new HashSet<>();
        int reads;
        int failures;
        String reject;
        final SharedPreferences preferences = proxy(SharedPreferences.class, (p, method, args) -> {
            if (method.getName().equals("getString")) { reads++; return null; }
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
            return proxy(XposedModuleInterface.PackageReadyParam.class, (p, method, args) -> {
                switch (method.getName()) {
                    case "getPackageName": return packageName;
                    case "getClassLoader": return ModernModuleTest.class.getClassLoader();
                    default: throw new AssertionError(method);
                }
            });
        }
        Method method(String name) {
            return hooks.keySet().stream().filter(m -> m.getName().equals(name)).findFirst().orElseThrow();
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
        System.out.println("PASS: " + assertions + " API 102 contract assertions");
    }
}
