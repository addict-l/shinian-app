# 拾年前端开发导航

前端按业务页面组织目录。入口为 `App/AIMemoirsApp.swift → ContentView.swift → JournalAppView.swift`。

| 目录 | 开发入口与职责 |
| --- | --- |
| `Features/Home` | 首页 `JournalHomeView.swift` |
| `Features/NewMemory` | 流程容器 `JournalComposeView.swift`；子目录 `AddPerson`、`SelectPerson`、`Chat`、`Review` 对应添加人物、选择人物、对话、预览与编辑 |
| `Features/FamilyFilm` | 家庭胶片主页面；时间线算法放 `Models`，本机头像存储放 `Stores` |
| `Features/Profile` | 我的主页面；设置与隐私说明放各自子目录 |
| `Features/Memories` | 全部回忆与已保存回忆详情 |
| `Features/FamilyMember` | 人物资料与人物关联回忆 |
| `App/Navigation` | 标签、路由、跨页面导航状态、底部导航栏 |
| `Shared/Stores` | 全局人物与回忆状态，由根视图创建一次并注入 |
| `Shared/Components` | 共用按钮、搜索、空态、错误态、人物与回忆展示组件 |
| `Shared/DesignSystem` | 颜色、字体、间距、页面背景与导航衔接规则 |
| `Shared/Formatting` | 日期、副标题和人物身份的展示格式 |
| `Models` | 跨页面及 API 使用的业务模型与人物请求草稿 |
| `Networking` | API 协议、请求客户端和后端数据适配器 |
| `PreviewSupport` | 仅 Debug 编译的设计预览数据，不写入真实数据库 |

## 维护约定

1. 一个独立页面一个文件；只被某个业务使用的服务、模型和组件放在该业务目录。
2. 多个业务共用的展示组件放 `Shared/Components`，不在组件里创建网络客户端或控制全局导航。
3. 远端数据通过 API 协议和状态对象访问；页面持有搜索、焦点、弹窗等 UI 状态。子页面通过绑定和回调与流程容器协作。
4. 人物与回忆共享状态由 `JournalAppView` 创建；子页面使用 `EnvironmentObject`，避免重复实例导致数据不同步。
5. 注释说明职责、依赖、状态生命周期和不直观的约束。新增通用样式优先更新设计系统。
6. Xcode 使用文件系统同步目录，新增或移动 Swift 文件会自动进入目标，无需手工维护源文件列表。当前按目录划分职责，仍是一个 App target，并非独立 Swift Package。

## 运行与验证

正常联调使用 `AIMemoirs` Scheme；`AIMemoirs-DesignPreview` 使用离线样例。测试源码、验证脚本与构建结果位于主工程同级的 `shinian-validation/`。

单元测试位于 `shinian-validation/tests/ios/AIMemoirsTests`；页面回归测试位于同目录下的 `AIMemoirsUITests/JournalUIFlowTests.swift`。该 UI 测试使用离线数据，覆盖九个页面、人物创建到保存的流程，以及键盘和导航栏下的输入框可见性。验证入口为 `shinian-validation/scripts/ios/check.sh`，运行 App 无需验证目录。
