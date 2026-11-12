# 锤锤 · libxposed API 102 适配版

基于 **锤锤 Smartisan 0.4-beta5** 制作的第三方适配项目，将原模块的 Legacy Xposed 实现迁移到 **libxposed API 102**，保留原有界面和环境快照格式。

感谢原模块作者及贡献者提供的基础功能。原始模块仓库：**[Xposed-Modules-Repo/com.fuck.android.rimet](https://github.com/Xposed-Modules-Repo/com.fuck.android.rimet)**。

本仓库维护新增的适配代码、APK 修改脚本和测试；这是基于原 APK 的二进制迁移工程，并非原作者发布的完整 Android Studio 源码工程，也不是官方更新版本。

## 当前状态

初始迁移测试版：`0.4-beta5-api102-test1`。自动构建的发布版本请见 **[GitHub Releases](https://github.com/lilu0826/Smartisan-Modern/releases)**。

- 已完成 API 102 入口、Hook、配置通信和激活检测迁移。
- 已通过编译、API 102 接口契约测试、定位对象转换测试、应用侧类加载隔离测试，以及 APK 静态和签名校验。
- **使用者已反馈迁移版可以正常使用。** 尚未收集其手机型号、Android 版本及具体框架构建号，不将此反馈扩大为对所有设备的兼容承诺。

## 适配内容

| 部分 | 迁移后的实现 |
| --- | --- |
| 模块注册 | `META-INF/xposed/java_init.list`、`module.prop`、`scope.list` |
| 生命周期 | `XposedModule`、`onModuleLoaded`、`onPackageReady` |
| 方法 Hook | API 102 的 `hook(...).intercept(...)` |
| 配置读取 | 框架 Remote Preferences，应用侧接入 service 102.0.0 |
| 激活检测 | 实际框架服务连接及 API 版本检测 |
| 定位对象 | 使用目标应用的类加载器创建，避免同名类无法转换 |
| 定位监听器 | 保留原监听器对象身份，避免影响移除和重新注册 |

六处基础入口 Hook 涉及高德定位客户端、Wi-Fi 信息及基站信息；定位监听器回调在注册时安装。钉钉另外在 `DtLocation.fromLocation` 和 `DtLocation.fromAMapLocation` 的结果出口应用快照，覆盖绕过高德客户端的系统定位路径。原有 Legacy 入口、`XposedHelpers`、`XSharedPreferences` 和模块自 Hook 激活检测已移除。

### 首次进入位置与刷新位置不一致

仅拦截高德客户端时，钉钉的系统定位仍可经 `DtLocation.fromLocation` 回传原位置，而高德刷新才应用快照，造成首次进入考勤页与刷新后位置不同。现在两个钉钉转换工厂都先执行原转换，再应用快照坐标、精度和地址，避免系统坐标转换再次作用于已保存的坐标。

结果保留钉钉对象类型、服务来源、业务状态、时间和 extras；快照缺失时保留原转换行为。新增 JVM 回归覆盖首次系统定位、随后高德刷新、不同类加载器、只有 String 构造器的钉钉结果类型，以及失败后原转换不重复执行。设备验收仍需保留既有页面缓存，检查首次进入和刷新全过程；接口或自建 listener 测试不能替代这一步。

## 运行要求

- 支持 **libxposed API 102** 的框架，请以框架实际显示的 API 版本为准。
- APK 最低 Android 版本声明为 Android 8.0（API 26）；实际可用版本还取决于框架及目标应用。
- 目标应用需要包含兼容的高德定位 SDK，并已加入模块作用域。

本适配版不支持仅提供 Legacy、API 100 或 API 101 的框架。未启用 API 102 热重载，更新模块后需重启目标进程。

## 安装

1. **备份原版快照后再卸载。** 快照通常位于 `/sdcard/Android/data/com.fuck.android.rimet/files/profiles`，请复制到电脑或应用数据目录以外的位置。
2. 安装适配版 APK。由于使用新的签名，不能直接覆盖作者签名的原版。
3. 在框架中启用模块并选择目标应用。
4. 打开模块，恢复或创建快照，重新选择需要使用的快照，等待同步到框架。
5. 强行停止并重新打开目标应用，验证功能。

构建产物默认位于 `output/app-general-api102-test1.apk`。仓库不跟踪 APK 二进制，下载源码不会附带安装包。

详细步骤见 [使用说明](output/使用说明.md)。

### 高德 SDK Key

原 APK 内置的高德 Key 可能绑定原作者签名。重新签名后，如果创建快照出现高德鉴权错误，需要使用与包名 `com.fuck.android.rimet` 和自己签名 SHA-1 匹配的 Android SDK Key，再调整构建资源中的 `amap_api_key`。

已有使用者反馈可用，但这不能保证旧 Key 在所有设备和网络环境下都有效。签名校验输出和[使用说明](output/使用说明.md)可用于排查当前测试包的签名。

## 从源码构建

也可以运行 `python tools/prepare_build.py` 自动获取下文指定的原始 APK、Apktool 和 Maven 依赖。所有下载均校验固定 SHA-256；已有文件哈希不一致时会停止构建。

构建脚本支持 **Windows 和 macOS**，需要 Python 3.12、JDK 17 和网络连接用于准备依赖。建议显式设置 `JAVA_HOME`；脚本不会修改系统默认 JDK。

### 1. 准备原始 APK

从[原始模块 Releases](https://github.com/Xposed-Modules-Repo/com.fuck.android.rimet/releases)获取对应的 `0.4-beta5` APK，放在仓库根目录，命名为 `app-general-release.apk`。

脚本只接受本次适配所用的原始文件，其 SHA-256 为：

```text
90c6bfaa674fe39e6eebf2fb929f4ca3833882b0db51486c8701cbe6d27eb854
```

若校验不一致，请检查版本和文件来源。不要直接跳过校验；不同 APK 的混淆符号及字节码结构可能不同。

### 2. 准备工具与依赖

将 `JAVA_HOME` 设置为本机 JDK 17 的安装目录，然后在仓库根目录执行：

```powershell
python tools/fetch_migration_deps.py
Invoke-WebRequest -Uri 'https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar' -OutFile 'tools/apktool.jar'
```

依赖下载脚本会获取 API、service、interface 102.0.0、Android 编译桩、D8/R8 和签名库。依赖版本、来源及固定哈希见 [dependencies.json](tools/migration/dependencies.json)；下载后必须通过哈希校验。

### 3. 构建与验证

```powershell
python migration/build.py
python migration/test.py
python migration/verify_apk.py
```

构建脚本每次从原始 APK 解码，应用带断言的修改，编译新增 Java 代码、生成 DEX、重新打包并签名。`io.github.libxposed:api` 仅用于编译，不会打入 APK。

输出位置：

| 文件或目录 | 用途 |
| --- | --- |
| `output/app-general-api102-test1.apk` | 迁移安装包 |
| `output/build-result.json` | APK 哈希和本次构建信息 |
| `output/static-verification.json` | 最终 APK 静态检查结果 |
| `migration/build/` | 每次构建的独立工作目录 |
| `migration/signing/local-test.p12` | 首次构建生成、后续复用的个人测试密钥 |

**妥善保留签名密钥。** 重新生成密钥会导致后续包无法覆盖已有的个人测试版。密钥和构建缓存已由 `.gitignore` 排除；签名脚本使用的是本地测试配置。

## 项目结构

```text
migration/
  src/                     API 102 适配代码
  tests/                   JVM 测试及模拟 Android/框架环境
  build.py                 APK 修改、编译和打包
  test.py                  JVM 测试入口
  verify_apk.py            二进制清单、DEX、资源及对齐校验
  SignApk.java              签名和签名验证
tools/
  prepare_build.py          下载并校验原 APK、Apktool 和依赖
  fetch_migration_deps.py   依赖准备
  migration/dependencies.json
output/
  使用说明.md
```

反编译工作区、原始 APK、生成 APK、第三方工具二进制和私钥均不提交到 Git。

## GitHub Actions 自动发布

工作流：[Build and release API 102](.github/workflows/release.yml)。使用 Windows runner、Python 3.12 和 JDK 17，自动下载已适配的原版 `11-0.4-beta5`，校验输入，构建签名 APK，执行测试与静态检查，再发布到 Releases。

### 触发方式

- **手动发布**：进入仓库 **Actions → Build and release API 102 → Run workflow**，选择 `main`，填写未使用过的标签（例如 `v0.4-beta5-api102.2`），默认发布正式 Release；需要预发布时再勾选 `prerelease`。
- **标签发布**：将 `v` 开头的版本标签推送到仓库，默认发布正式 Release。原版版本名里的 `beta5` 不影响适配版的发布状态。

版本名取标签去掉开头的 `v`；Android `versionCode` 使用 `1000 + github.run_number` 自动递增。不要删除后重新创建工作流来重置运行编号。已有同名 Release 会使流程停止，避免覆盖旧版本；已存在的标签必须指向本次构建的提交。

Release 包含 APK、安装说明、构建来源和哈希信息、静态检查结果与 `SHA256SUMS.txt`。附件先上传到草稿 Release，全部成功后才公开；发布步骤失败时，已验证的附件仍保存在 Actions Artifact 中 14 天。若失败留下了草稿，确认原因后删除该草稿再重试，或使用新标签。

### 持久签名

发布必须配置两个 **Actions repository secrets**：

| Secret | 内容 |
| --- | --- |
| `KEYSTORE_BASE64` | PKCS#12 签名文件的 Base64 内容 |
| `KEYSTORE_PASSWORD` | 对应密钥库密码；工作流默认私钥密码相同、别名为 `migration` |

本仓库发布使用现有个人测试版的签名，可覆盖同一签名的测试包。Fork 本仓库时需要自行配置自己的 Secrets，不能继承原仓库 Secrets，也不能覆盖其他签名的安装包。

如需手动配置现有本地测试密钥，在 PowerShell 中执行以下命令，将内容复制到 Secret 编辑框（不要提交密钥或 Base64 文本）：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path 'migration/signing/local-test.p12'))) | Set-Clipboard
```

签名文件仅在构建步骤还原到 runner 临时目录，构建结束后删除，不会上传到 Artifact 或 Release。CI 缺少密钥会直接失败，不会临时生成新密钥导致后续无法覆盖安装。

本地也可通过 `APP_VERSION_NAME`、`APP_VERSION_CODE` 设置版本，通过 `SIGNING_KEYSTORE`、`KEYSTORE_PASSWORD`、`KEY_PASSWORD`、`KEY_ALIAS` 使用现有的其他签名。

## 测试与问题反馈

JVM 测试使用真实 API 102 接口与模拟框架，覆盖 Hook 去重、配置缺失时调用原方法、空及继承监听器、可恢复的 Hook 失败隔离、配置连接重试、跨类加载器对象转换以及快照不被修改。测试用 Android 类不会打入最终 APK。

静态检查覆盖旧 API 引用清除、API 未被内嵌、类定义无重复、原 Kotlin 服务注册文件保留、二进制清单和资源对齐。构建过程中另会验证 APK v2/v3 签名。

这些检查不能替代真实 ART Hook、Binder 通信和目标应用功能测试。`build-result.json` 中的 `runtime_tested` 表示构建流程是否执行过设备测试，不代表没有使用者成功运行过。

反馈问题时请提供手机型号、Android 版本、框架分支/构建号及 API 版本、目标应用版本、复现步骤，以及 `Smartisan102` 相关日志。分享日志前请遮盖位置、账号等个人信息。

## 鸣谢

- **[锤锤 Smartisan 原始模块](https://github.com/Xposed-Modules-Repo/com.fuck.android.rimet)**：感谢原作者和贡献者实现原有界面、环境快照及定位功能；本项目在其 APK 基础上完成 API 适配。
- **[libxposed](https://github.com/libxposed/api)** 与 **[libxposed service](https://github.com/libxposed/service)**：提供现代模块 API 和框架通信接口。
- **[Apktool](https://github.com/iBotPeaches/Apktool)**、**[JADX](https://github.com/skylot/jadx)**：支持 APK 分析和重新构建。

原模块及其内置第三方组件的权利和许可归各自作者；本适配项目不改变这些归属。请遵循原项目的用途说明，在有授权的开发与测试环境中使用。
