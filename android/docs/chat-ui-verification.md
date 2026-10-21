# 聊天滚动与全屏界面验证

日期：2026-10-21。范围为本轮 Android 界面调整，沿用现有纸色、字体和聊天布局，一次提交人工审核。

## 本轮行为

- 移除人生采访输入框的“慢慢讲，我在听…”浮动标签，输入提示只保留一处。
- 普通聊天与人生采访进入页面后显示最新内容；发送、收到回复、长回复和键盘改变可视高度时继续跟随底部。
- 用户向上翻阅历史时暂停跟随；点击“回到最新”或主动发送后恢复。
- 应用及全屏弹层隐藏状态栏与导航栏，关闭导航栏的灰色对比度遮罩；保留键盘避让及刘海安全区域。系统边缘手势仍可短暂唤出系统栏。

软键盘打开时，输入法可显示它自己的系统导航区域。本轮要求状态栏持续隐藏、消息与输入框不被键盘遮住；键盘关闭后再检查应用导航栏隐藏和底部纸色背景。

交互参考 [AI SDK Conversation](https://elements.ai-sdk.dev/components/conversation) 与 [assistant-ui Thread](https://www.assistant-ui.com/docs/vue/primitives/thread) 的底部跟随与历史阅读行为；窗口处理依据 [Android 沉浸式界面](https://developer.android.com/develop/ui/views/layout/immersive) 和 [Compose edge-to-edge](https://developer.android.com/develop/ui/compose/system/setup-e2e) 官方说明。

## 验证方式

复用 `Shinian_Pixel_9_API_36` 模拟器。`ChatViewportTest` 使用生产聊天页面、控制器和窗口策略，终止于内存 OkHttp interceptor，不创建网络连接，不操作真实账号。

先安装上一版 APK 复现问题：长历史下最新人生采访消息不可见，输入框仍存在浮动标签。再安装本轮构建执行新行为断言，并保存实际截图。

测试源码：[ChatViewportTest.kt](../app/src/androidTest/java/cn/shinian/app/ui/chat/ChatViewportTest.kt)。日志和截图保存于 [本轮验证目录](../artifacts/chat-viewport-20261021/)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Debug APK 与仪器测试 APK 构建 | 通过 | [构建日志](../artifacts/chat-viewport-20261021/checked-build.log) |
| JVM 单元测试 | 50 通过，0 失败、错误或跳过 | [保存的测试报告](../artifacts/chat-viewport-20261021/reports/unit-tests/index.html) |
| Android Lint | 0 Error、92 Warning、1 Hint | [保存的报告](../artifacts/chat-viewport-20261021/reports/lint-results-debug.html) |
| 聊天与窗口仪器测试 | 5 通过，0 失败 | [最终日志](../artifacts/chat-viewport-20261021/final-instrumentation.log) |

五个用例覆盖普通聊天与人生采访的初次定位、发送/回复、70 行长回复尾部、真实软件键盘开合、历史阅读位置不变、“回到最新”和主动发送恢复，以及窗口重新进入和聊天历史全屏弹窗。键盘打开时以实际 IME inset 核对输入框没有被遮住。

初轮失败日志保留在验证目录。已修正测试数据以完整助手回复结尾，避免被识别为待重试讲述；使用包含最终滚动修正的同一构建重新验证。模拟器测试临时允许硬键盘连接时显示软件键盘，结束后恢复原设置。

截图复核还发现 Android 首次全屏教育提示遮挡了部分画面。通过可见的系统“Got it”按钮正常确认后，再次运行同一组五个用例，全部通过；审核入口仅使用随后截取的 12 张无提示遮挡图片。此前截图与日志保留为诊断证据。

## 人工复核

安装 [最新 APK](../releases/拾年-Android-1.0.1-20261021-debug.apk)，进入有历史记录的采访或普通聊天，连续发送几条消息，打开、关闭键盘，再向上翻阅历史并返回最新。

实际截图见 [本轮截图审核页](../artifacts/chat-viewport-20261021/review.html)。

本轮自动化验证仅覆盖上述 Android 模拟器，未独立验证鸿蒙卓易通容器外层系统界面。本轮不改动 iOS、后端及采访业务规则，不部署云端服务。

2026-10-21，用户明确回复“审核通过，把这次聊天界面的修改 commit 并推送到 main”。依据 [项目开发流程](../../.agents/skills/project-development/SKILL.md)，本轮已完成人工审核，获准正式提交并推送 `main`。
