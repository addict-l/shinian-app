# 拾年 · 温馨版 SwiftUI

按提供的 15 页设计稿实现的 iOS 前端，使用暖纸背景、赤陶杏色、鼠尾草绿、Noto Serif SC 宋体和苹方字体。水彩插画、人物照片和线性 SVG 图标全部随 App 打包。

## 直接运行

打开 `AIMemoirs.xcodeproj`，选择 **AIMemoirs** Scheme，运行到已有的 **iPhone 17 Pro（iOS 26.5）**。正常启动使用真实后端和家庭账号；已有登录信息会自动恢复，首次安装需输入真实密码。设备使用 Keychain 保存凭据，模拟器使用自己的本机存储。项目不包含家庭密码或 AI 密钥。

服务器地址位于 `Config/Info.plist` 的 `AI_MEMORIES_API_URL`；如需连接其他环境，可设置同名 Scheme 环境变量。正式连接要求 HTTPS；Debug 仅允许 localhost / 127.0.0.1 使用 HTTP。

## 已接入功能

- 家庭账号登录、登录恢复、退出，以及凭据失效后返回登录页。
- 家庭人物查询、添加、生日校验、准备 AI 开场、删除和搜索。
- 每位人物的真实聊天窗口、历史恢复、AI 回复、语音转写、照片选择与上传、多照片消息、失败重试和未发送内容恢复。
- 回忆草稿生成、修改和重新生成；确认保存后更新首页、人物列表、回忆列表、胶片和统计。
- 已保存回忆查询、筛选、阅读、多照片查看、标题正文及时间地点感受编辑、照片增删、版本冲突核对和删除。
- 家庭胶片、全部家人目录、人物资料及参与人物统计。故事年份来自真实故事时间，不以创建时间补充未知年份。
- 回忆录制作设置云端同步、断网保留与重试、跨设备版本核对、三种封面、照片选择与取景、故事和照片排序、字号、整本 PDF 预览及系统分享／存储。
- 本机显示名称、个人头像和家庭人物头像。

回忆录只收录以所选家人为主人物的已保存故事。封面缩略图、取景预览和导出 PDF 共用相同排版。照片上传至家庭服务用于展示和回忆录，对话文字交给配置的 AI 整理，照片不发送给 AI 分析。

显示名称和人物头像延续原项目的本机保存方式；批量家庭数据导出、账号权限管理及人物资料修改没有现有后端接口，未新增虚构接口。删除人物和回忆前会显示确认。

## 离线设计预览

**AIMemoirs-DesignPreview** Scheme 仅在 Debug 中启用 `JournalDemoAPI`。只有显式设置 `AI_MEMORIES_DESIGN_SCREEN` 或 `--design-screen` 才会使用示例数据；正常 Debug 和所有 Release 启动均连接真实后端。预览登录不会修改真实账号凭据，预览删除不会清理真实聊天草稿。

预览包含 4 位家人、18 段回忆，人物与回忆改动仅保留在该次预览中。回忆录预览缓存按预览范围隔离。

## 页面入口

| 设计稿页面 | 入口 | 截图参数 |
| --- | --- | --- |
| 01 欢迎回家 | 启动／设置退出 | `login` |
| 02 首页 | 首页标签 | `home` |
| 03 首次使用空态 | 指定空态启动，按钮进入添加人物 | `home-empty` |
| 04 添加人物 | 新的回忆 → 添加新的家庭人物 | `add` |
| 05 选择人物 | 新的回忆标签，左滑可删除 | `select` |
| 06 AI 对话 | 点击人物 | `chat` |
| 07 回忆预览 | 对话 → 整理成一段回忆 | `review` |
| 08 所有回忆 | 首页查看全部／我的全部回忆 | `memories` |
| 09 回忆详情和操作菜单 | 点击回忆 → 右上角更多 | `story-actions` |
| 10 家庭胶片 | 家庭胶片标签 | `film` |
| 11 人物资料 | 点击胶片人物名称 | `person` |
| 12 制作回忆录 | 人物资料 → 制作回忆录 | `memoir` |
| 13 我的 | 我的标签 | `profile` |
| 14 设置 | 我的 → 设置 | `settings` |
| 15 隐私与数据 | 我的 → 隐私与数据 | `privacy` |

`AIMemoirs-DesignPreview` Scheme 默认从登录页开始。要直接查看某页，可以在 Scheme 的 Run → Arguments → Environment Variables 中设置 `AI_MEMORIES_DESIGN_SCREEN` 为上表参数，或传入 `--design-screen person` 这类启动参数。`story` 可直接查看不带菜单的详情页。

设计稿的内容基准为 393 × 852；iPhone 17 Pro 使用设备真实的状态栏、灵动岛和安全区域，内容随可用宽度布局，不绘制假的设备边框或状态栏。

## 工程结构

- `App`：真实服务装配、独立 Debug 预览入口、四个标签和共享导航状态。
- `Features`：首页、新回忆、家庭胶片、人物、回忆、回忆录和个人页面。
- `Shared/DesignSystem`：颜色、字体、间距、卡片、页面背景。
- `Shared/Components`：导航、按钮、头像、照片、搜索、标签和回忆正文。
- `PreviewSupport/JournalDemoAPI.swift`：仅显式 Debug 设计预览使用的演示数据源。
- `Assets.xcassets`、`Resources/Fonts`：随包图片、图标和字体。
- `Networking`：复用原项目的真实 HTTP 后端适配器，统一注入人物、聊天、回忆和回忆录。

Xcode 使用文件系统同步目录；新 Swift 文件和普通资源会自动进入 App target。

## 编译和截图

```sh
xcodebuild -project AIMemoirs.xcodeproj -scheme AIMemoirs \
  -configuration Debug \
  -destination 'platform=iOS Simulator,id=82915145-6254-4561-9028-8F8F8D636B89' \
  -derivedDataPath /tmp/shinian-ui-build CODE_SIGNING_ALLOWED=NO build

python3 scripts/capture-design.py \
  --app /tmp/shinian-ui-build/Build/Products/Debug-iphonesimulator/AIMemoirs.app
```

截图脚本仅使用已启动的 iPhone 17 Pro，不会创建或启动其他模拟器。15 页截图在 `DesignVerification/screenshots`，可打开 `DesignVerification/index.html` 查看总览。

## 底部导航更新

四个入口统一使用无底色的线性图标，选中项采用杏色图标和中等字重文字，未选中项采用灰棕色。“新的回忆”与其他入口遵循同一规则。导航底座为实心暖白胶囊，取消材质模糊与图标独立阴影。

## 功能验证

`Tests` 保存新版登录与界面回归检查；App 工程仍只有 App target。生成独立验证工程：

```sh
python3 scripts/make-validation-project.py
xcodebuild -project /tmp/shinian-betterui-checks/AIMemoirs.xcodeproj \
  -scheme AIMemoirs -configuration Debug \
  -destination 'platform=iOS Simulator,id=82915145-6254-4561-9028-8F8F8D636B89' \
  -derivedDataPath /tmp/shinian-betterui-checks/DerivedData \
  CODE_SIGNING_ALLOWED=NO -parallel-testing-enabled NO \
  -only-testing:AIMemoirsTests test
```

`--legacy-tests` 和 `--legacy-preview` 可附带原项目已有的状态、协议、照片和 PDF 回归测试，原文件不会被修改。生成目录不可位于产品目录内。

真实写入与 AI 联调测试需要另行准备独立临时数据库和 API，通过 SSH 转发到 `http://localhost:17655`，再以 `--isolated-api` 生成 `AIMemoirs-Isolated` Scheme。测试硬性校验地址，默认不执行真实写入；结束后销毁临时 API、数据库和测试照片。正常云端界面检查只读取已有家庭资料。

所有本次模拟器验证均固定已有 iPhone 17 Pro；没有新建或切换其他设备。麦克风实际普通话识别效果仍需要真机及用户授权验证。
