"""Download the exact supported upstream APK and Apktool, then locked Maven dependencies."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
INPUTS = [
    ('app-general-release.apk',
     'https://github.com/Xposed-Modules-Repo/com.fuck.android.rimet/releases/download/11-0.4-beta5/app-general-release.apk',
     '90c6bfaa674fe39e6eebf2fb929f4ca3833882b0db51486c8701cbe6d27eb854'),
    ('tools/apktool.jar',
     'https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar',
     'dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423'),
]

def main():
    for relative, url, expected in INPUTS:
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            request = urllib.request.Request(url, headers={'User-Agent': 'Smartisan-Modern-build'})
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Downloaded input SHA-256 mismatch: ' + relative)
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Existing input SHA-256 mismatch: ' + relative)
        print('Verified:', relative, flush=True)
    subprocess.run([sys.executable, str(ROOT / 'tools/fetch_migration_deps.py')], check=True)

if __name__ == '__main__':
    main()
