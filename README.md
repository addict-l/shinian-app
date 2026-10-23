# 拾年（Shinian）

一款帮助家庭记录真实故事的 iOS / Android App：添加家人，通过 AI 对话梳理回忆，附上照片，校对并保存草稿，按人物制作和导出 PDF 回忆录。

**iOS：用 Xcode 打开 `ios/AIMemoirs.xcodeproj`。Android：用 Android Studio 打开 `android/`。** 两端默认连接现有阿里云后端；无需在本机部署数据库或配置大模型密钥。

文档从[总导航](docs/README.md)进入，按[整个项目的骨架](docs/project/README.md)、[第一次大提交 T01–T07](docs/phase-1/README.md)、[第二次大提交](docs/phase-2/README.md)分层。`ios/legacy/` 保留第一阶段交付工程，后续主线为 `ios/`。

## 最近修复（2026-10-23）

**已修复采访入口提示“数据库暂时不可用”、无法开始采访的问题。** 当家庭已有较大的采访记录时，原会话列表查询会对含大段 JSON 的完整记录排序，触发 MySQL 1038（排序内存不足），导致采访入口返回 HTTP 503。修复后先排序轻量 ID，再读取完整内容，保留原有家庭筛选和会话顺序。

修复提交：[`a1ecee6`](https://github.com/addict-l/shinian-app/commit/a1ecee61eae633898f1ba3a7200a630ca66a32c2)，已发布到真实阿里云。本地及云端测试均 Ran 80、skip 1、失败/错误 0；正式 HTTPS 与现有模拟器已验证可进入采访第一题。业务数据、模型配置及固定键盘/输入法设置保持原样。详细根因、验证和 Claude 接续要求见[修复回传记录](docs/phase-2/interview-optimization/handoffs/2026-10-23-session-list-sort.md)。

## 下载最新版本

在 GitHub 页面选择分支 **main → Code → Download ZIP**，解压后打开 `ios/AIMemoirs.xcodeproj`。已下载的 ZIP 不会自动更新，需要重新下载。

也可以使用 Git：

```sh
git clone --branch main https://github.com/addict-l/shinian-app.git
cd shinian-app
open ios/AIMemoirs.xcodeproj
```

已经通过 Git 下载过项目：在原仓库运行 `git pull --ff-only origin main`。可用 `git log -1 --oneline` 查看当前提交；有自己的改动时先保留，避免覆盖。

## iOS 运行

- Mac 和 Xcode；交付验证使用 Xcode 26.6，工程最低支持 iOS 18.1。
- 已安装 iPhone 模拟器运行时；当前指定验证设备为 iPhone 17 Pro / iOS 26.0。
- 网络能访问现有阿里云 API。
- 使用自己的家庭账号登录或注册；密码不保存在工程中。

1. 打开 `ios/AIMemoirs.xcodeproj`，等待 Xcode 索引完成。
2. 顶部 Scheme 选择 **AIMemoirs**，设备选择 **iPhone 模拟器**。
3. 按 `Command + R`。模拟器运行无需登录开发者账号或选择开发团队。
4. App 打开后，登录或注册家庭账号。
5. 从“新的回忆”选择或创建家人；“家庭胶片 → 人物头像”可浏览回忆，或制作／继续制作回忆录。

`AIMemoirs-DesignPreview` 是离线设计样例，不用于验证真实云端数据。老师登录现有家庭账号后会看到已有回忆，新增与编辑也保存在同一家庭。

第一阶段交付时的试用步骤和验证范围见 [T07 老师指南](docs/phase-1/t07/t07-delivery.md)；新版主线的开发及验证入口见 [客户端说明](ios/AIMemoirs/README.md)。

## Android 运行

1. Android Studio 打开 `android/`，Gradle JDK 选择 **JDK 21**。
2. 安装 Android SDK Platform 36 和 Build Tools 35.0.0，等待 Gradle 同步。
3. 选择 `app` 和安卓模拟器／设备后运行。最低 Android 8.0（API 26）。

命令行构建：`cd android && ./scripts/build.sh`。重新构建的 APK 输出在 `android/app/build/outputs/apk/debug/`；当前仅保留的[最新安装包](android/releases/拾年-Android-1.0.1-20261021-debug.apk)统一放在 `android/releases/`，截图与日志放在 `android/artifacts/`，均不提交 Git。

详细步骤见 [Android 工程说明](android/README.md)，当前审核材料见 [Android 验收导航](android/docs/README.md)。

## 当前功能

- 每位家人一个聊天窗口，恢复最近 20 条消息；当前回忆的分析仍使用完整讲述。
- 信息分析模型与对话模型协作，支持自然引导、就绪判断、明确整理请求和第一人称草稿。
- 一次最多 9 张照片；发送后即时显示文字，失败保留输入和重试状态。照片存储，不送入 AI。
- 草稿校对、确认保存、已保存回忆编辑与删除；创建家人时准备开场白，保存后承接下一篇。
- 每人一本回忆录，封面／内容／整本预览三步制作，三种封面、A5、14／16 pt 字号、目录与连续页码。
- 短篇文字（含标题及时间地点）占内容区半页以内时，首图与文字同页；其余和长文照片继续分页。
- 制作设置自动保存，处理离线待同步和版本冲突，分享前核对故事与设置，导出预览中的 PDF。

长篇草稿整理与时间联动已进入第二阶段 B02/B03；新版制作界面、PDF 精细排版和童年采访的具体完成状态见 [第二阶段导航](docs/phase-2/README.md)。

## 项目内容与云端版本

```text
ios/                              iOS 工程、源码、资源、测试和设计验收
  AIMemoirs.xcodeproj              Xcode 主线入口
  legacy/                         第一期 iOS 历史工程
android/                          Android Studio / Gradle 工程
  app/                            Kotlin / Compose 源码、资源和测试
  scripts/                        构建与验证脚本
  docs/                           Android 实现说明与验收记录
  releases/                       仅保留最新安卓安装包（Git 忽略）
  artifacts/                      本机截图与日志（Git 忽略）
cloud-deployment/                 两端共用的后端、部署配置和接口契约
docs/                             共用业务文档、阶段计划和历史记录
tools/                            共用采访与后端验证工具
```

前端默认 API：`https://aimemory.47-82-83-74.nip.io`。后端使用 FastAPI、MySQL 8、Docker Compose、Nginx HTTPS 和后端模型接口，固定单 worker。GitHub 推送不会自动更新云服务器；[T07 版本清单](docs/phase-1/t07/delivery-manifest.json)保留第一阶段快照，后续模型切换见[二期部署记录](docs/phase-2/records/cloud-deployment-record.md)。童年三层采访仍为独立候选试点。

目录迁移对应关系见 [工程目录说明](docs/project/directory-layout.md)。

GitHub 保留运行和维护所需源码、资源、示例配置、依赖版本及数据库迁移。本地 `shinian-validation` 保存测试源码、验证工程、日志、截图、临时 PDF 和构建缓存，不参与老师构建，也不上传本仓库。生产密码、API 密钥、证书私钥、数据库及真实照片备份保留在受控环境。

## 常见问题

- **没有 iPhone 模拟器：**在 Xcode Settings 的 Components／Platforms 中安装 iOS Simulator Runtime，然后选择模拟器；菜单名称随 Xcode 版本可能不同。
- **提示 Team／provisioning profile：**检查顶部是否误选真机。模拟器不需要开发团队；真机安装需要在 Signing & Capabilities 选择自己的团队和可用 Bundle ID，步骤见交付指南。
- **登录失败：**使用维护者单独提供的当前密码。可在“我的 → 设置”退出后重新登录。
- **无法连接：**访问现有 API 的 `/health` 检查连接；业务接口需要有效的家庭会话。
- **无法选择照片：**模拟器相册需要先有图片，可把图片拖入模拟器导入。

## 开发与维护资料

- [文档总导航](docs/README.md)
- [iOS 工程说明](ios/README.md)、[Android 工程说明](android/README.md)
- [后端职责](cloud-deployment/backend/README.md)
- [云端部署、备份和回退](cloud-deployment/backend/DEPLOY_ALIYUN.md)
- [T07 已确认交付边界](docs/phase-1/t07/t07-requirements.md)
- [一期交付与验证](docs/phase-1/README.md)、[二期计划与验收](docs/phase-2/README.md)
- [本地日志与验证归档](docs/project/local-artifacts.md)

老师自己的 Mac、真机中文语音和实际跨设备体验需要相应环境的人工验收；本机干净下载与模拟器验证不能代替这些实际体验。
