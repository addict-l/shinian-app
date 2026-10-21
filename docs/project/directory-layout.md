# 工程目录说明

2026-10-21 起，客户端按平台归拢。iOS 用 Xcode 打开 `ios/AIMemoirs.xcodeproj`；Android 用 Android Studio 打开 `android/`。

| 目录 | 内容 |
| --- | --- |
| [ios/](../../ios/README.md) | iOS 主线工程、Swift 源码、图片字体、配置、测试与设计验证 |
| [ios/legacy/](../../ios/legacy/README.md) | 第一期 iOS 历史工程 |
| [android/](../../android/README.md) | Gradle 工程、Kotlin 源码、图片字体与测试 |
| [android/docs/](../../android/docs/README.md) | Android 实现说明与整体验收记录 |
| `android/releases/` | 仅保留最新 Android 安装包、版本元数据与校验值，Git 忽略 |
| `ios/artifacts/`、`android/artifacts/` | 各端本机构建与验证产物，Git 忽略 |
| `cloud-deployment/` | 两端共用的后端、部署文件与 API 契约 |
| `docs/`、`tools/` | 共用业务文档、历史阶段记录与后端工具 |

## 路径迁移

| 原路径 | 新路径 |
| --- | --- |
| `front-betterui/` | `ios/` |
| `frontend/` | `ios/legacy/` |
| `docs/phase-3/android/` | `android/docs/` |
| `artifacts/android-20261021/` | `android/artifacts/android-20261021/` |

迁移前后的 553 个文件已核对 SHA-256 与文件权限。原有未提交源码、资源、测试及验收材料完整迁移；历史发布清单、验收日志内的旧路径保留当时记录，查找时按上表换算。

## 整理验证

- iOS：从 `ios/AIMemoirs.xcodeproj` 完成 Debug 模拟器构建，并在指定的 iPhone 17 Pro / iOS 26.0 安装、启动成功。构建日志位于 `ios/artifacts/directory-layout-20261021/build.log`。
- iOS 历史工程可正常解析；主线验证生成脚本可从新路径生成包含 App、单元测试和 UI 测试的独立工程。
- Android：从 `android/` 完成 `:app:assembleDebug`，在已有 API 36 模拟器安装、启动成功。日志位于 `android/artifacts/directory-layout-20261021/`。
- 当前导航文档的 143 处本地链接通过检查；迁移文件无遗漏、权限不变，源码与资源内容未改。
- 更新了运行脚本、两份项目环境说明及本机外部旧版验证入口；iOS 测试源码显式保留在 Git 跟踪范围内，各端私有验证材料仍被忽略。

本次仅调整本机目录与相关路径，没有后端部署或业务数据修改；整理结果等待用户统一审核，尚未创建提交。
