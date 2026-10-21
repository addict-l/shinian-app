# B04：回忆录制作、家庭胶片与访谈界面验收

日期：2026-10-13。基线：已推送 main 的 B03 `512915c`。状态：实现与相关验证完成，等待第 27 问人工审核；尚未 commit 或推送。

## 本次变化

回忆录封面页沿用用户通过的第三版 A 布局：200 pt 宽 A5 书封居中，保存状态收进导航栏，三项编辑入口放在书封下方统一分组，下一步固定底部。封面样式、照片与取景、书名与副标题各自打开编辑面板。缩略图来自现有真实 PDF renderer，预览与导出使用同一套封面数据。

故事页按章节编号、标题、时间、照片与操作行组织内容；阅读设置打开独立面板，可选择 14/16 pt。保留章节拖动、上下移动、恢复时间排序确认，以及照片选择、上下移动和拖动排序。整本预览显示当前页与总页数、翻阅/缩放提示、重新生成和分享入口；分享继续校验当前故事和设置版本。

家庭胶片把“查看全部家人”移到家人统计旁，人物行右侧使用小圆加号，点击范围为 44 pt。移除占据整个画格的虚线添加框；空人物仍可从加号或空胶卷进入访谈。完整目录、搜索、横向胶卷、人物照片与原导航继续可用。

AI 回复改为小标签加正文，没有气泡背景或边框；用户文字气泡、照片、相册、语音、输入、发送、失败重试和草稿保存沿用原有流程。

## 范围

本块只改客户端界面，不改变 API、模型、访谈规则或数据结构。模型沿用 B01/B02 的 DeepSeek Flash（ds flash）。PDF 成品的三种封面、扉页、目录、正文与照片组合精修属于 B05；本块未修改 `MemoirPDFRenderer.swift`，界面截图不能代替 B05 成品验收。

## 实际验证

验证材料位于 `/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/`。19 项模型/数据检查和 12 项独立 UI 场景全部通过。

| 场景 | 结果与证据 |
| --- | --- |
| 封面、标题/副标题、拼贴、三张封面取景、14 pt、章节移动、照片选择/移动、取消恢复排序、实际 PDF 与系统分享 | 真实阿里云接口通过，最终补跑 `ui8-tests.log` |
| 全部家人入口、小加号直达正确人物、零故事人物不可制书且仍可访谈 | 真实阿里云接口通过，`ui4-tests.log` |
| 最大 Dynamic Type、长标题/副标题、横屏固定按钮、导航标题与保存状态不重叠 | 截图复核后修正导航栏字号约束，最终补跑 `ui8-tests.log` |
| AI 无气泡与键盘下相册/语音/发送入口 | 通过，`ui4-tests.log` |
| 素雅封面禁用照片操作、系统相册导入独立封面 | 真实阿里云上传和保存通过，`ui5-tests.log` |
| 第二设备修改云端设置、本机保存冲突、查看完整对照、采用云端版本 | 最大字号下真实阿里云版本冲突与恢复通过，`ui5-tests.log` |
| 大字号照片管理与发送 | 通过，`ui5-tests.log` |
| 空家庭的首位人物入口 | 离线演示通过，`ui6-tests.log` |
| 中断回复后离线重启、唯一用户气泡、手动重试入口 | 离线演示通过，`ui6-tests.log` |
| 现有封面取景/拼贴/PDF 分享回归 | 适配新入口后通过，`ui7-tests.log` |
| 保存草稿后仍在同一人物访谈、下一故事不沿用旧整理入口 | 离线演示通过，`ui7-tests.log` |
| 照片与文字先出现，完整 AI 回复随后出现，历史照片继续保留 | 延迟演示通过，`ui7-tests.log` |

- 主线 Xcode 工程构建通过：`build-final.log`。
- 19 项 Swift Testing 通过：家庭归属/时间顺序/人物照片、回忆录旧协议解码、离线设置与相册封面持久化、响应丢失后的幂等协调、版本冲突、照片失败重试、分享前版本核对及现有 A5 排版回归。日志 `model-tests2.log`，结果 `/tmp/shinian-b04-model2.xcresult`。
- 指定的原 iPhone 17 Pro，iOS 26.5，UDID `82915145-6254-4561-9028-8F8F8D636B89`。
- 阿里云联调复用独立 `shinian-b03-isolated` 服务，经本机 17655 隧道连接云端回环端口 18003；继续使用已验证 B03 接口，未部署正式后端。
- 云端测试人物、故事和照片都是合成素材。照片比例覆盖横图、竖图和宽图；手机相册选择使用模拟器内已准备的合成素材。正式家庭未写入。
- `cloud-book-readback.json` 可复核实际版本、书名/副标题、相册封面独立 ID、手动章节顺序、照片顺序/排除项与 14 pt 字号。`cloud-book-before-final.json` 另保留拼贴的三张封面照片及取景设置。

UI 场景按去重后的 12 项统计，分批结果映射在 `final-ui-results.json`。历史失败日志保留：开发期修正了分组后的子控件识别、嵌套照片取景面板；旧测试更新了编辑入口、当前 22 pt 页边距/6 pt 照片间距、已有历史照片及演示故事文案，受影响场景均已补跑通过。截图复核另外发现最大字号导航标题与保存状态重叠，已限制紧凑导航栏的字号上限，正文和编辑区域仍支持最大辅助字号，并补跑边界及三步流程。语音入口检查不代表已进行真机录音验收。

云端镜像读取结果见 `cloud-image-readback.log`：独立服务仍为 `223d80f85085`，正式服务仍为 `5d02956a447f`。本块没有正式发布；没有新增协议或数据库迁移，不重复执行与 B04 无关的后端整套测试。主线源码和 renderer 未改动核对见 `source-manifest.json`。

## 截图

以下均为原模拟器中实际 App 的截图。暖纸封面与访谈使用内置演示素材；阿里云照片联调使用合成色块，便于区分比例、顺序与取景。

![放大的书封与下方三个编辑入口](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/preview-memoir-cover-grouped.png)

[故事与照片](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cloud-chapters.png) · [整本预览](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cloud-pdf-preview.png) · [系统分享](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cloud-share.png)

[家庭目录与人物加号](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cloud-family.png) · [AI 无气泡访谈](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-interview-no-bubble.png) · [键盘与输入栏](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-interview-keyboard.png)

[封面样式](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cover-styles.png) · [取景](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cover-crop.png) · [照片选择与排序](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-story-photos.png) · [手机相册导入](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-phone-imported-cover.png)

[空家庭](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-empty-family.png) · [最大字号](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-large-cover.png) · [版本对照](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/b04-cloud-conflict-comparison.png) · [中断回复恢复](/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b04/screenshots/t04-restored-pending-message.png)

## 人工检查

1. 在原模拟器测试版打开“家庭胶片”，检查统计右侧目录入口、人物加号和胶卷；打开全部家人搜索 `B04照片验收` 或 `B04空回忆`。
2. 进入 `B04照片验收` 的人物页，点击制作回忆录。检查居中的书封、三项分组入口和固定底部按钮；分别编辑样式、书名/副标题、照片与取景。
3. 进入故事与照片步骤，检查阅读设置、章节上下移动、照片选择和排序；打开恢复时间排序确认，再取消，检查手动顺序保持。
4. 生成整本预览，检查页数、翻阅、缩放和系统分享面板。成品排版的进一步精修在 B05 单独审核。
5. 点击某人的小加号，检查 AI 无气泡、用户气泡/照片和输入栏；大字号及横屏情况下滚动查看所有入口。

审核通过后的拟提交标题：`优化回忆录制作与家庭胶片访谈界面（B04）`。
