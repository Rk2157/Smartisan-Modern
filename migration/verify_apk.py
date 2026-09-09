"""Static verification of the final APK, including actual binary manifest and DEX tables."""
import hashlib
import json
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parent.parent

def strings_in_dex(data):
    count, offset = struct.unpack_from('<II', data, 56)
    result = []
    for index in range(count):
        pos = struct.unpack_from('<I', data, offset + index * 4)[0]
        while data[pos] & 128:
            pos += 1
        pos += 1
        result.append(data[pos:data.index(b'\0', pos)].decode('utf-8', 'replace'))
    return result

def defined_classes(data):
    strings = strings_in_dex(data)
    count, offset = struct.unpack_from('<II', data, 64)
    types = [strings[struct.unpack_from('<I', data, offset + i * 4)[0]] for i in range(count)]
    count, offset = struct.unpack_from('<II', data, 96)
    return {types[struct.unpack_from('<I', data, offset + i * 32)[0]] for i in range(count)}

def manifest_elements(data):
    pool = []
    offset = 8
    result = []
    while offset < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, offset)
        assert size >= header and size > 0
        if kind == 1:
            count, _, flags, start, _ = struct.unpack_from('<IIIII', data, offset + 8)
            for index in range(count):
                pos = offset + start + struct.unpack_from('<I', data, offset + header + index * 4)[0]
                if flags & 0x100:
                    pos += 2 if data[pos] & 128 else 1
                    length = data[pos]
                    pos += 1
                    if length & 128:
                        length = ((length & 127) << 8) | data[pos]
                        pos += 1
                    pool.append(data[pos:pos+length].decode('utf-8'))
                else:
                    length = struct.unpack_from('<H', data, pos)[0]
                    pos += 2
                    if length & 0x8000:
                        length = ((length & 0x7fff) << 16) | struct.unpack_from('<H', data, pos)[0]
                        pos += 2
                    pool.append(data[pos:pos+length*2].decode('utf-16-le'))
        elif kind == 0x102:
            _, name, attr_start, attr_size, attr_count = struct.unpack_from('<IIHHH', data, offset + 16)
            attributes = {}
            for index in range(attr_count):
                pos = offset + 16 + attr_start + index * attr_size
                _, attr_name, raw = struct.unpack_from('<III', data, pos)
                value_type, value = struct.unpack_from('<BI', data, pos + 15)
                attributes[pool[attr_name]] = (pool[raw] if raw != 0xffffffff else
                                               pool[value] if value_type == 3 else value)
            result.append((pool[name], attributes))
        offset += size
    return result

def verify():
    build = json.loads((ROOT / 'output/build-result.json').read_text())
    apk = ROOT / 'output' / build['apk']
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == build['sha256']
    with zipfile.ZipFile(apk) as archive, zipfile.ZipFile(ROOT / 'app-general-release.apk') as original:
        original_android = {c for name in original.namelist() if name.endswith('.dex')
                            for c in defined_classes(original.read(name)) if c.startswith('Landroid/')}
        assert archive.testzip() is None
        assert 'assets/xposed_init' not in archive.namelist()
        assert archive.read('META-INF/xposed/java_init.list').decode().strip() == 'com.fuck.android.rimet.modern.ModernModule'
        properties = archive.read('META-INF/xposed/module.prop').decode()
        assert 'minApiVersion=102\n' in properties and 'targetApiVersion=102\n' in properties
        classes = set()
        dex_count = 0
        for name in archive.namelist():
            if name.endswith('.dex'):
                data = archive.read(name)
                assert not any(marker in data for marker in [b'de/robv/android/xposed', b'android/app/AndroidAppHelper'])
                defined = defined_classes(data)
                assert not classes.intersection(defined), 'Duplicate DEX classes'
                assert not any(c.startswith('Lio/github/libxposed/api/') for c in defined), 'Compile-only API accidentally packaged'
                # R8 left a few Android compatibility stubs in the original APK. Only those are allowed.
                android_classes = {c for c in defined if c.startswith('Landroid/')}
                assert android_classes.issubset(original_android), 'Test fixture accidentally packaged'
                if name != 'classes.dex':
                    assert not android_classes, 'Test fixture in migration DEX'
                classes.update(defined)
                dex_count += 1
        for required in ['com/fuck/android/rimet/modern/ModernModule', 'com/fuck/android/rimet/modern/AppBridge',
                         'io/github/libxposed/service/XposedProvider', 'io/github/libxposed/service/IXposedService',
                         'com/fuck/android/rimet/profile/Profile']:
            assert 'L' + required + ';' in classes, required
        assert not any(c.startswith('Lcom/fuck/android/rimet/core/CoreLoader') for c in classes)
        service_files = [n for n in original.namelist() if n.startswith('META-INF/services/')]
        for name in service_files:
            assert archive.read(name) == original.read(name), 'Original service registration changed: '+name
        assert archive.read('assets/secret') == original.read('assets/secret')
        elements = manifest_elements(archive.read('AndroidManifest.xml'))
        manifest = next(attrs for name, attrs in elements if name == 'manifest')
        assert manifest['package'] == 'com.fuck.android.rimet'
        assert manifest['versionCode'] == 12 and manifest['versionName'] == '0.4-beta5-api102-test1'
        assert not any(name == 'meta-data' and attrs.get('name', '').startswith('xposed') for name, attrs in elements)
        assert any(name == 'provider' and attrs.get('name') == 'io.github.libxposed.service.XposedProvider'
                   and attrs.get('authorities') == 'com.fuck.android.rimet.XposedService'
                   and attrs.get('exported') == 0xffffffff for name, attrs in elements)
        app = next(attrs for name, attrs in elements if name == 'application')
        assert 'description' in app
        with apk.open('rb') as stream:
            for info in archive.infolist():
                if info.compress_type == zipfile.ZIP_STORED:
                    stream.seek(info.header_offset + 26)
                    name_length, extra_length = struct.unpack('<HH', stream.read(4))
                    assert (info.header_offset + 30 + name_length + extra_length) % 4 == 0, info.filename
        assert archive.getinfo('resources.arsc').compress_type == zipfile.ZIP_STORED
    report = {'apk': apk.name, 'sha256': build['sha256'], 'dex_files': dex_count,
              'defined_classes': len(classes), 'legacy_references': 0, 'api_102_embedded': False,
              'test_fixtures_embedded': False, 'original_service_files_preserved': len(service_files),
              'binary_manifest_verified': True, 'stored_entries_aligned': True,
              'android_device_tested': False}
    (ROOT / 'output/static-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    verify()
