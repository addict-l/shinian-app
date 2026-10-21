# 拾年 iOS 工程

当前 iOS 客户端统一放在本目录。使用 Xcode 打开 [AIMemoirs.xcodeproj](AIMemoirs.xcodeproj)，选择 `AIMemoirs` Scheme；后续 iOS 开发以此工程为准。

| 目录或文件 | 用途 |
| --- | --- |
| [AIMemoirs.xcodeproj](AIMemoirs.xcodeproj) | 当前 App 工程和共享 Scheme |
| [AIMemoirs/](AIMemoirs/) | SwiftUI 源码、图片、字体与图标；[功能及开发说明](AIMemoirs/README.md) |
| [Config/](Config/) | App 配置与后端地址 |
| [Tests/](Tests/) | 主线单元测试与界面回归源码 |
| [docs/](docs/chat-auto-scroll-verification.md) | 本轮聊天自动滚动的行为、验证与审核记录 |
| [scripts/](scripts/) | 独立验证工程生成与设计截图脚本 |
| [DesignVerification/](DesignVerification/) | 设计核对页面、截图与历史说明 |
| [legacy/](legacy/) | 此前交付和后端联调客户端，供历史复核 |

从仓库根目录构建，复用当前已有的 iPhone 17 Pro / iOS 26.0：

```sh
cd ios
xcodebuild -project AIMemoirs.xcodeproj -scheme AIMemoirs \
  -configuration Debug \
  -destination 'platform=iOS Simulator,id=8801F7F7-7154-4AEB-88F2-1E77A8393190' \
  -derivedDataPath /tmp/shinian-ios-build CODE_SIGNING_ALLOWED=NO build
```

`AIMemoirs-DesignPreview` Scheme 使用离线设计样例。真实账号、照片上传和云端联调使用 `AIMemoirs`；运行环境见 [项目环境说明](../.agents/skills/project-development/references/project-environment.md)。

共同的业务与交付文档位于 [docs/](../docs/README.md)，后端位于 [cloud-deployment/backend/](../cloud-deployment/backend/README.md)，Android 工程位于 [android/](../android/README.md)。
