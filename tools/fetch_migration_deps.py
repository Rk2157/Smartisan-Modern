import concurrent.futures, hashlib, pathlib, urllib.request, zipfile, json

ROOT = pathlib.Path(__file__).resolve().parent / 'migration'
ROOT.mkdir(exist_ok=True)
URLS = {
    'api.aar': 'https://repo.maven.apache.org/maven2/io/github/libxposed/api/102.0.0/api-102.0.0.aar',
    'api-sources.jar': 'https://repo.maven.apache.org/maven2/io/github/libxposed/api/102.0.0/api-102.0.0-sources.jar',
    'service.aar': 'https://repo.maven.apache.org/maven2/io/github/libxposed/service/102.0.0/service-102.0.0.aar',
    'service-sources.jar': 'https://repo.maven.apache.org/maven2/io/github/libxposed/service/102.0.0/service-102.0.0-sources.jar',
    'interface.aar': 'https://repo.maven.apache.org/maven2/io/github/libxposed/interface/102.0.0/interface-102.0.0.aar',
    'android.jar': 'https://repo.maven.apache.org/maven2/com/google/android/android/4.1.1.4/android-4.1.1.4.jar',
    'r8.jar': 'https://dl.google.com/dl/android/maven2/com/android/tools/r8/8.5.35/r8-8.5.35.jar',
    'apksigner.jar': 'https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/8.5.2/apksig-8.5.2.jar',
}

def fetch(item):
    name, url = item
    path = ROOT / name
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    print(name, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)
    if name.endswith('.aar') or name.endswith('-sources.jar'):
        with zipfile.ZipFile(path) as archive:
            archive.extractall(ROOT / name.rsplit('.', 1)[0])

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(fetch, URLS.items()):
            pass
    (ROOT / 'dependencies.json').write_text(json.dumps({name: {'url': url, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name, url in URLS.items()}, indent=2))
