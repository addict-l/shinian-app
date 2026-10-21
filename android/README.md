# 拾年 Android

Android Studio 原生 Kotlin / Jetpack Compose 工程。复现基线为同仓库 [`ios/`](../ios/) 当前工作区源码，使用相同 HTTPS 家庭账号服务。

本目录统一存放 Android 工程：`app/` 为源码与资源，`scripts/` 为构建及验证脚本，[`docs/`](docs/README.md) 为实现和验收说明，`releases/` 仅保留最新安装包，`artifacts/` 为本机截图与验证产物。

## 打开与构建

1. Android Studio 打开本目录，安装 Android SDK Platform 36 和 Build Tools 35.0.0。
2. Gradle JDK 选择 JDK 21。此工程的 Gradle 8.13 不支持 Studio Rabbit 自带的 JBR 25，不能直接使用该运行时构建。
3. 同步后运行 `app`。最低 Android 8.0（API 26），目标 API 36。

命令行执行：

```sh
./scripts/build.sh
./scripts/build.sh :app:connectedDebugAndroidTest
```

脚本优先使用兼容的完整 `JAVA_HOME`；需要包含 `javac` 和 `jlink`。本机已安装 Temurin JDK 21。SDK、机器路径和 IDE 设置不提交到 Git。

最新安装包统一存放在 [`releases/拾年-Android-1.0.0-20261021-debug.apk`](releases/拾年-Android-1.0.0-20261021-debug.apk)，版本与校验信息在同目录。重新构建时，Gradle 会生成 `app/build/outputs/apk/debug/app-debug.apk`。正式分发版本需使用项目所有者的签名配置。

## 功能与数据

- 家庭账号注册、登录、恢复、当前设备退出；Android Keystore 加密会话，独立账号缓存。
- 首页、人物管理、家庭胶片、回忆搜索与筛选、阅读、多图、编辑、删除与版本冲突。
- 人生骨架、核对与更正、六个采访模块；文字、普通话听写、照片与聊天草稿恢复。
- 草稿预览、编辑、时间联动、重生成及显式保存。
- 回忆录三步制作、三种封面、照片取景、故事与照片排序、字号及跨设备设置核对。
- A5 中文 PDF 本地分页、目录链接、整本预览、保存及系统分享。
- 关怀模式的大字简化页面，独立三入口导航；个人头像和展示名保存在本机。
- 共用深色全屏照片选择器：四列网格、相册切换、有序勾选与完整预览；聊天和回忆支持多选，头像和封面使用单选。按授权范围访问图库，保留系统选图入口。

API 默认值由 `app/build.gradle.kts` 中的 `API_BASE_URL` 提供。生产包只使用 HTTPS；图片通过带家庭 Bearer 会话的同源私有媒体接口读取。

采访规则由服务器返回。客户端不携带另一套题库，不更改线上采访策略。语音听写使用设备提供的中文识别服务；设备未安装服务或拒绝麦克风权限时，页面给出恢复提示并保留文字输入。

## 验证

JVM 测试覆盖认证恢复、设备会话隔离、幂等与版本合同、UTF-16 时间联动、回忆录时间排序。Android 仪器测试覆盖表单与浏览交互、Keystore、中文 PDF 分页及目录导出。

真实云端验证仅使用新建的独立测试家庭：

```sh
python3 scripts/verify_live_backend.py --execute
```

运行会生成独立家庭及验收故事。私有凭据仅保存到本工程内 Git 忽略的 `artifacts/` 目录，禁止提交。截图、测试结果和仍需真机核验的项目见[本次验收记录](docs/verification.md)。

## 资源许可

Noto Serif SC 与 `ios/` 使用相同的 OFL 字体文件，许可在 `app/src/main/res/raw/noto_serif_sc_license.txt`。沿用原工程图标和图片。Android 正文使用系统中文无衬线字体；Apple 的 PingFang 系统字体不随 Android 包分发。
