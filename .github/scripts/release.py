"""Small release helper. GitHub event values are data, never interpolated into shell code."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'release-assets'

def api(path):
    request = urllib.request.Request('https://api.github.com/' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise

def prepare():
    tag = os.environ.get('INPUT_TAG') if os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch' else os.environ['GITHUB_REF_NAME']
    if not tag or not re.fullmatch(r'v[0-9][0-9A-Za-z.+_-]{0,79}', tag):
        raise ValueError('Use a version tag such as v0.4-beta5-api102.1')
    repo = os.environ['GITHUB_REPOSITORY']
    encoded = urllib.parse.quote(tag, safe='')
    if api(f'repos/{repo}/releases/tags/{encoded}') is not None:
        raise ValueError('Release already exists; use a new version tag')
    ref = api(f'repos/{repo}/git/ref/tags/{encoded}')
    if ref is not None:
        obj = ref['object']
        while obj['type'] == 'tag':
            obj = api(f'repos/{repo}/git/tags/{obj["sha"]}')['object']
        current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if obj['sha'] != current:
            raise ValueError('Existing tag does not point at the checked-out commit')
    # The upstream version contains "beta5"; it does not determine this adaptation's release status.
    prerelease = (os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
                  and os.environ.get('INPUT_PRERELEASE', 'false').lower() == 'true')
    version_code = 1000 + int(os.environ['GITHUB_RUN_NUMBER'])
    if version_code > 2100000000:
        raise ValueError('Android versionCode limit exceeded')
    values = {'RELEASE_TAG': tag, 'APP_VERSION_NAME': tag[1:], 'APP_VERSION_CODE': str(version_code),
              'RELEASE_PRERELEASE': str(prerelease).lower()}
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
        for key, value in values.items():
            stream.write(f'{key}={value}\n')
    print(json.dumps(values))

def package():
    build = json.loads((ROOT / 'output/build-result.json').read_text(encoding='utf-8'))
    verification = json.loads((ROOT / 'output/static-verification.json').read_text(encoding='utf-8'))
    apk = ROOT / 'output' / build['apk']
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if digest != build['sha256'] or digest != verification['sha256']:
        raise ValueError('Final APK differs from verified build')
    if build['version_name'] != os.environ['APP_VERSION_NAME'] or build['version_code'] != int(os.environ['APP_VERSION_CODE']):
        raise ValueError('APK version does not match the release')
    ASSETS.mkdir(exist_ok=False)
    shutil.copyfile(apk, ASSETS / apk.name)
    shutil.copyfile(ROOT / 'output/使用说明.md', ASSETS / 'INSTALL.md')
    shutil.copyfile(ROOT / 'output/static-verification.json', ASSETS / 'static-verification.json')
    public_build = {key: value for key, value in build.items() if key != 'build_directory'}
    public_build['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    public_build['workflow_run'] = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    (ASSETS / 'build-info.json').write_text(json.dumps(public_build, indent=2), encoding='utf-8')
    checksums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(ASSETS.iterdir()))
    (ASSETS / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    notes = f'''## Smartisan Modern {build['version_name']}

基于原模块 **0.4-beta5**，适配 **libxposed API 102**。

- Android versionCode：`{build['version_code']}`。
- 已通过 API 接口测试、定位对象转换测试、APK 静态检查和 v2/v3 签名校验。
- 云端构建未进行手机测试；此前适配测试版已有使用者反馈可用。
- 使用仓库配置的持久签名。替换原作者签名的原版前，请先备份快照；相同签名的适配版可覆盖升级。
- 高德 Key 如绑定其他签名，创建快照可能需要另行配置自己的 Key。

安装后在支持 API 102 的框架中启用模块、勾选作用域，打开模块并选择快照，然后重启目标应用。

附件包含 APK、安装说明、构建信息、静态校验报告及 SHA-256 校验清单。

感谢[锤锤 Smartisan 原作者及贡献者](https://github.com/Xposed-Modules-Repo/com.fuck.android.rimet)，以及 [libxposed](https://github.com/libxposed/api)。这是第三方适配版。
'''
    (ROOT / 'output/release-notes.md').write_text(notes, encoding='utf-8')

def publish():
    repo = os.environ['GITHUB_REPOSITORY']
    tag = os.environ['RELEASE_TAG']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Stage attachments on a draft first; publish only after every upload succeeds.
    command = ['gh', 'release', 'create', tag, '--repo', repo, '--target', head, '--draft',
               '--title', 'Smartisan Modern ' + os.environ['APP_VERSION_NAME'],
               '--notes-file', str(ROOT / 'output/release-notes.md')]
    command += [str(p) for p in sorted(ASSETS.iterdir())]
    subprocess.run(command, check=True)
    command = ['gh', 'release', 'edit', tag, '--repo', repo, '--draft=false',
               '--prerelease=' + os.environ['RELEASE_PRERELEASE']]
    subprocess.run(command, check=True)

if __name__ == '__main__':
    {'prepare': prepare, 'package': package, 'publish': publish}[sys.argv[1]]()
