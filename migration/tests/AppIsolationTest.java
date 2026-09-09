public final class AppIsolationTest {
    public static void main(String[] args) throws Exception {
        try {
            Class.forName("io.github.libxposed.api.XposedModule");
            throw new AssertionError("Module API must be absent from app-side test classpath");
        } catch (ClassNotFoundException expected) {}
        if (com.fuck.android.rimet.modern.AppBridge.isActive())
            throw new AssertionError("Disconnected service cannot report active");
        Class.forName("com.fuck.android.rimet.modern.ProfileStorage");
        System.out.println("PASS: app-side classes load without framework module API; disconnected status is false");
    }
}
