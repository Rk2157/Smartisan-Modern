import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;
import java.io.File;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.Collections;

public final class SignApk {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("sign")) {
            KeyStore keys = KeyStore.getInstance("PKCS12");
            try (FileInputStream stream = new FileInputStream(args[1])) {
                keys.load(stream, "local-test-only".toCharArray());
            }
            ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder("smartisan-api102-test",
                    (PrivateKey) keys.getKey("migration", "local-test-only".toCharArray()),
                    Collections.singletonList((X509Certificate) keys.getCertificate("migration"))).build();
            new ApkSigner.Builder(Collections.singletonList(signer)).setInputApk(new File(args[2]))
                    .setOutputApk(new File(args[3])).setMinSdkVersion(26)
                    .setV1SigningEnabled(true).setV2SigningEnabled(true).setV3SigningEnabled(true)
                    .setV4SigningEnabled(false).build().sign();
            verify(args[3]);
        } else verify(args[1]);
    }

    private static void verify(String path) throws Exception {
        ApkVerifier.Result result = new ApkVerifier.Builder(new File(path)).setMinCheckedPlatformVersion(26).build().verify();
        System.out.println("verified=" + result.isVerified() + " v1=" + result.isVerifiedUsingV1Scheme()
                + " v2=" + result.isVerifiedUsingV2Scheme() + " v3=" + result.isVerifiedUsingV3Scheme());
        for (Object error : result.getErrors()) System.out.println("ERROR: " + error);
        for (Object warning : result.getWarnings()) System.out.println("WARNING: " + warning);
        for (X509Certificate cert : result.getSignerCertificates()) {
            byte[] digest = java.security.MessageDigest.getInstance("SHA-1").digest(cert.getEncoded());
            System.out.println("signer SHA-1=" + java.util.HexFormat.ofDelimiter(":").withUpperCase().formatHex(digest));
        }
        if (!result.isVerified()) throw new IllegalStateException("Signature verification failed");
    }
}
