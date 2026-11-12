# API 102 migration

This is a reproducible binary migration of the supplied `app-general-release.apk`, not a recovered full Android Studio project. The original UI and snapshot model are retained as decoded bytecode; the Xposed implementation is replaced by the Java sources under `src/`.

`build.py` verifies the original input hash, decodes it with Apktool, applies asserted bytecode/manifest replacements, compiles against `io.github.libxposed:api:102.0.0`, adds `service:102.0.0` and `interface:102.0.0`, and produces a signed APK. The API itself is compile-only and is not embedded.

Run from the workspace root:

```powershell
python migration/build.py
python migration/test.py
python migration/verify_apk.py
```

Requirements: Python 3.12, JDK 17 (`JAVA_HOME` can override the local default), and the tools already downloaded under `tools/`. Maven dependency URLs and hashes are in `tools/migration/dependencies.json`. The build starts from the original APK on every run. The local test key is reused to permit updates between your own test builds.

The JVM tests use the actual API 102 classes with a fake framework and minimal Android fixtures; fixtures are excluded from APK compilation. Tests cover registration, callback identity, failure isolation, disconnected app status, cross-classloader location conversion, and DingTalk's first SYSTEM result followed by GAODE refresh. The DingTalk factory hooks run after the original coordinate conversion and retain the returned model's type and business metadata. The original converter runs once, including when snapshot application fails. These tests do not execute ART hooks, the actual Android Parcel format, Binder IPC, or a previously cached attendance page. Device acceptance must include first entry with existing page caches, rather than only direct API or synthetic listener calls.

JDK executable discovery is shared in `java_tools.py`: `JAVA_HOME` takes priority, otherwise tools are located on PATH. Windows uses the `.exe` suffix; macOS uses the regular executable names. Set `JAVA_HOME` to JDK 17 explicitly when a version manager defaults to another JDK.

User-facing installation instructions and the AMap key/signature limitation are in `output/使用说明.md`. Final APK metadata and static checks are in `output/build-result.json` and `output/static-verification.json`.
