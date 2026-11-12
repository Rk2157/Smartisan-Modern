"""Rebuild the supplied APK with native libxposed API 102 code. Python 3.12 + JDK 17."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

from java_tools import java_tool

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / 'tools/migration'
JAVA = java_tool('java')
JAVAC = java_tool('javac')
KEYTOOL = java_tool('keytool')
BUILD = ROOT / 'migration/build' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
STAGE = BUILD / 'decoded'
OUT = ROOT / 'output'
ORIGINAL_SHA = '90c6bfaa674fe39e6eebf2fb929f4ca3833882b0db51486c8701cbe6d27eb854'
NS = 'http://schemas.android.com/apk/res/android'
VERSION_NAME = os.environ.get('APP_VERSION_NAME', '0.4-beta5-api102-test1')
VERSION_CODE = int(os.environ.get('APP_VERSION_CODE', '12'))
if not re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,79}', VERSION_NAME):
    raise ValueError('Invalid APP_VERSION_NAME')
if not 12 <= VERSION_CODE <= 2100000000:
    raise ValueError('APP_VERSION_CODE must be between 12 and 2100000000')

def run(*args):
    print('RUN', ' '.join(str(x) for x in args), flush=True)
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True)

def replace_method(path, signature, body):
    text = path.read_text(encoding='utf-8')
    pattern = r'^\.method ' + re.escape(signature) + r'\n.*?^\.end method'
    replacement = '.method ' + signature + '\n' + body.strip() + '\n.end method'
    text, count = re.subn(pattern, lambda _: replacement, text, flags=re.M | re.S)
    assert count == 1, (path, signature, count)
    path.write_text(text, encoding='utf-8')

def patch():
    import xml.etree.ElementTree as ET
    ET.register_namespace('android', NS)
    manifest = STAGE / 'AndroidManifest.xml'
    tree = ET.parse(manifest)
    app = tree.getroot().find('application')
    for child in list(app):
        if child.tag == 'meta-data' and child.get('{'+NS+'}name', '').startswith('xposed'):
            app.remove(child)
    app.set('{'+NS+'}description', '@string/module_description')
    ET.SubElement(app, 'provider', {
        '{'+NS+'}name': 'io.github.libxposed.service.XposedProvider',
        '{'+NS+'}authorities': 'com.fuck.android.rimet.XposedService',
        '{'+NS+'}exported': 'true',
    })
    tree.write(manifest, encoding='utf-8', xml_declaration=True)
    yml = STAGE / 'apktool.yml'
    original = yml.read_text(encoding='utf-8')
    assert 'versionCode: 11' in original and 'versionName: 0.4-beta5' in original
    yml.write_text(original.replace('versionCode: 11', f'versionCode: {VERSION_CODE}')
                   .replace('versionName: 0.4-beta5', f'versionName: {VERSION_NAME}'), encoding='utf-8')
    (STAGE / 'assets/xposed_init').unlink()
    obsolete = [
        'a.1/a.smali', 'a.1/a$a.smali', 'a.1/a$b.smali', 'a.1/a$c.smali',
        'b.1/a.smali', 'b.1/a$a.smali',
        'com/fuck/android/rimet/core/CoreLoader.smali',
        'com/fuck/android/rimet/core/CoreLoader$a.smali',
        'com/fuck/android/rimet/core/CoreLoader$b.smali',
        'com/amap/api/location/AMapLocationClientS1.smali',
        'com/amap/api/location/AMapLocationClientS1$getLastKnownLocation$1.smali',
        'com/amap/api/location/AMapLocationClientS1$setLocationListener$1.smali',
        'com/amap/api/location/AMapLocationListenerS1.smali',
    ]
    for name in obsolete:
        path = (STAGE / 'smali' / name).resolve()
        assert path.is_relative_to(STAGE.resolve()) and path.suffix == '.smali'
        path.unlink()
    replace_method(STAGE / 'smali/k1.1/c.smali', 'public final f()Lcom/fuck/android/rimet/profile/Profile;', '''
    .locals 1
    iget-object v0, p0, Lk1/c;->a:Landroid/content/Context;
    invoke-static {v0}, Lcom/fuck/android/rimet/modern/ProfileStorage;->readLocal(Landroid/content/Context;)Ljava/lang/Object;
    move-result-object v0
    check-cast v0, Lcom/fuck/android/rimet/profile/Profile;
    return-object v0
''')
    replace_method(STAGE / 'smali/k1.1/c.smali', 'public final h(Lcom/fuck/android/rimet/profile/Profile;)Z', '''
    .locals 1
    iget-object v0, p0, Lk1/c;->a:Landroid/content/Context;
    invoke-static {v0, p1}, Lcom/fuck/android/rimet/modern/ProfileStorage;->select(Landroid/content/Context;Ljava/lang/Object;)Z
    move-result v0
    return v0
''')
    replace_method(STAGE / 'smali/com/fuck/android/rimet/util/ModuleUtils.smali', 'public final isActive()Z', '''
    .locals 1
    invoke-static {}, Lcom/fuck/android/rimet/modern/AppBridge;->isActive()Z
    move-result v0
    return v0
''')
    application = STAGE / 'smali/com/fuck/android/rimet/SmartisanApplication.smali'
    text = application.read_text(encoding='utf-8')
    anchor = 'invoke-super {p0}, Landroid/app/Application;->onCreate()V'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '\n\n    invoke-static {p0}, Lcom/fuck/android/rimet/modern/AppBridge;->init(Landroid/content/Context;)V')
    application.write_text(text, encoding='utf-8')
    for path in (STAGE / 'smali').rglob('*.smali'):
        text = path.read_text(encoding='utf-8')
        for forbidden in ('de/robv/android/xposed', 'android/app/AndroidAppHelper', 'Lcom/fuck/android/rimet/core/CoreLoader;',
                          'Lcom/amap/api/location/AMapLocationClientS1;', 'Lcom/amap/api/location/AMapLocationListenerS1;'):
            assert forbidden not in text, (path, forbidden)

def aligned_zip(source, dest, dex):
    modern = {
        'META-INF/xposed/java_init.list': b'com.fuck.android.rimet.modern.ModernModule\n',
        'META-INF/xposed/scope.list': b'com.alibaba.android.rimet\n',
        'META-INF/xposed/module.prop': b'minApiVersion=102\ntargetApiVersion=102\nstaticScope=false\n',
    }
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(dest, 'w') as output:
        def keep(name):
            upper = name.upper()
            signature = upper == 'META-INF/MANIFEST.MF' or (upper.startswith('META-INF/') and
                        upper.endswith(('.SF', '.RSA', '.DSA', '.EC')))
            return not signature and not name.startswith(('META-INF/xposed/', 'assets/dexopt/'))
        entries = [(info.filename, archive.read(info.filename), info.compress_type)
                   for info in archive.infolist() if keep(info.filename)]
        entries += [(name, data, zipfile.ZIP_DEFLATED) for name, data in modern.items()]
        entries += [('classes2.dex', dex.read_bytes(), zipfile.ZIP_STORED)]
        for name, data, compression in entries:
            info = zipfile.ZipInfo(name, (2026, 9, 9, 0, 0, 0))
            info.compress_type = compression
            if compression == zipfile.ZIP_STORED:
                # Android 11+ requires an uncompressed, 4-byte aligned resources.arsc.
                start = output.fp.tell() + 30 + len(name.encode('utf-8'))
                pad = (-start) % 4
                if pad:
                    info.extra = struct.pack('<HH', 0xCAFE, pad) + bytes(pad)
            output.writestr(info, data)

def main():
    assert hashlib.sha256((ROOT / 'app-general-release.apk').read_bytes()).hexdigest() == ORIGINAL_SHA
    keys = Path(os.environ.get('SIGNING_KEYSTORE', str(ROOT / 'migration/signing/local-test.p12'))).resolve()
    if (os.environ.get('CI') == 'true' or 'SIGNING_KEYSTORE' in os.environ) and not keys.is_file():
        raise RuntimeError('CI requires an existing signing key; configure Actions signing secrets')
    BUILD.mkdir(parents=True)
    OUT.mkdir(exist_ok=True)
    # Decode the immutable input every time; do not rely on editable inspection output.
    run(JAVA, '-jar', ROOT / 'tools/apktool.jar', 'd', ROOT / 'app-general-release.apk',
        '-o', STAGE, '-p', ROOT / 'tools/framework')
    patch()
    classes = BUILD / 'classes'
    classes.mkdir()
    classpath = os.pathsep.join(str(DEPS / p) for p in ['android.jar', 'api/classes.jar', 'service/classes.jar', 'interface/classes.jar'])
    sources = sorted((ROOT / 'migration/src').rglob('*.java'))
    run(JAVAC, '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-cp', classpath, '-d', classes, *sources)
    for source in sources:
        expected = classes / source.relative_to(ROOT / 'migration/src').with_suffix('.class')
        assert expected.is_file(), ('Compiler did not produce expected class', expected)
    program = BUILD / 'modern.jar'
    with zipfile.ZipFile(program, 'w') as archive:
        for file in classes.rglob('*.class'):
            archive.write(file, file.relative_to(classes).as_posix())
    dex = BUILD / 'dex'
    dex.mkdir()
    run(JAVA, '-cp', DEPS / 'r8.jar', 'com.android.tools.r8.D8', '--release', '--min-api', '26',
        '--lib', DEPS / 'android.jar', '--classpath', DEPS / 'api/classes.jar', '--output', dex,
        program, DEPS / 'service/classes.jar', DEPS / 'interface/classes.jar')
    run(JAVA, '-jar', ROOT / 'tools/apktool.jar', 'b', STAGE, '-p', ROOT / 'tools/framework', '-o', BUILD / 'base.apk')
    aligned_zip(BUILD / 'base.apk', BUILD / 'aligned.apk', dex / 'classes.dex')
    if not keys.exists():
        keys.parent.mkdir(parents=True, exist_ok=True)
        run(KEYTOOL, '-genkeypair', '-keystore', keys, '-storetype', 'PKCS12',
            '-storepass', 'local-test-only', '-keypass', 'local-test-only', '-alias', 'migration',
            '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
            '-dname', 'CN=Smartisan API102 Local Test,OU=Personal migration,O=Local,C=CN', '-noprompt')
    run(JAVAC, '-cp', DEPS / 'apksigner.jar', '-d', classes, ROOT / 'migration/SignApk.java')
    filename = ('app-general-api102-test1.apk' if VERSION_NAME == '0.4-beta5-api102-test1'
                else f'Smartisan-Modern-{VERSION_NAME}.apk')
    apk = OUT / filename
    run(JAVA, '-cp', os.pathsep.join([str(classes), str(DEPS / 'apksigner.jar')]), 'SignApk',
        'sign', keys, BUILD / 'aligned.apk', apk)
    manifest = {'original_sha256': ORIGINAL_SHA, 'apk': apk.name,
                'version_name': VERSION_NAME, 'version_code': VERSION_CODE,
                'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'build_directory': str(BUILD),
                'runtime_tested': False}
    (OUT / 'build-result.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2), flush=True)

if __name__ == '__main__':
    main()
