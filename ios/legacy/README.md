# 旧版 iOS 工程

本目录保存原 `frontend/` 工程及其源码、资源与配置，用于此前交付、后端联调和历史验收复核。当前主线工程位于 [../AIMemoirs.xcodeproj](../AIMemoirs.xcodeproj)，开发入口见 [iOS 工程说明](../README.md)。

复核旧版时，使用 Xcode 打开本目录的 [AIMemoirs.xcodeproj](AIMemoirs.xcodeproj)，选择 `AIMemoirs` Scheme。旧版的页面和维护说明保存在 [AIMemoirs/README.md](AIMemoirs/README.md)。

同级仓库 `shinian-validation/scripts/ios/check.sh` 和 `scripts/ios/make_validation_project.py` 保留对此旧版工程的验证；当前主线使用 `ios/scripts/make-validation-project.py` 生成独立验证工程。共同的阶段记录从 [文档导航](../../docs/README.md) 查阅。
