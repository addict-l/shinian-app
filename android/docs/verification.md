# Android 原生复刻验收记录

记录日期：2026-10-21（Asia/Shanghai）。复刻基线为同仓库 `ios/` 当前源码；Android 工程位于 [`android/`](../README.md)，使用原 HTTPS 家庭账号服务。本记录区分已通过的客户端验证、现有云端问题和仍需真机检查的项目。

本轮沿用用户最新确认：完整实现后进行一次整体人工审核。当前尚未完成整体审核，未正式 commit、未 push。工程、APK 和截图作为同一整体提交审核。

整体审核期间追加的照片界面对齐已纳入同一安装包，详见 [照片界面补充验证](photo-ui-verification.md) 与 [实际照片流程截图](../artifacts/android-20261021/photo-ui-review.html)。选图预览、上传消息、网格与大图均以当前 iOS 为基准。

随后已按用户的微信参考替换默认选图入口，见 [微信式选图验证](wechat-picker-verification.md)、[新安装包](../releases/拾年-Android-1.0.0-20261021-debug.apk) 和 [截图](../artifacts/android-20261021/wechat-picker-review.html)。发送后的应用内照片样式继续沿用 iOS 基准。

## 本地与模拟器验证

| 验证项 | 当前结果 | 证据与覆盖范围 |
| --- | --- | --- |
| JVM 单元测试 | **50 通过，0 失败、0 错误、0 跳过** | [测试报告](../app/build/reports/tests/testDebugUnitTest/index.html)、[最终构建日志](../artifacts/android-20261021/build-final.log)。覆盖认证恢复与账号隔离、真实 HTTP 契约、幂等与版本、UTF-16 时间联动、回忆录排序及 PDF Unicode 映射。 |
| Android Lint | **0 Error、92 Warning、1 Hint** | [HTML 报告](../app/build/reports/lint-results-debug.html)、[XML 报告](../app/build/reports/lint-results-debug.xml)。包含微信式图库新增的 2 条 UseKtx 建议，仍有警告，不能写为零问题。 |
| 核心仪器测试 | **24 项全部通过** | [照片修正版回归日志](../artifacts/android-20261021/photo-ui-core-final.log)。含原 17 项及新增 7 项照片布局、管理、错误重试和上传中断恢复测试。原验证覆盖 Keystore、认证与浏览交互、草稿明确保存/时间联动、关怀模式、PDF 中文分页/长封面、真实目录与缩放手势，以及跨 UID 文件临时授权。 |
| 真实双图上传 UI | **1 项通过** | [照片联调日志](../artifacts/android-20261021/photo-ui-live-upload.log)。同一独立家庭，实际选图回调读取、压缩、私有上传、单条双图消息核对、认证下载与大图打开关闭。 |
| 真实云端 UI 端到端 | **1 项通过** | [端到端日志](../artifacts/android-20261021/instrumentation-live.log)。包含独立家庭登录、恢复、人物与回忆浏览、回忆录三步制作/PDF、设置与关怀模式、采访页可达。 |
| 小屏与大字号 | **3 项通过** | [运行日志](../artifacts/android-20261021/instrumentation-small-large-font.log)。960×1920、426 dpi（约 360dp 宽）、系统字号 2.0；登录/注册、长姓名关怀人物操作，以及关怀模式保存后的阅读/回首页/继续记录操作可达。 |
| 横屏 | **2 项通过** | [运行日志](../artifacts/android-20261021/instrumentation-landscape.log)。2424×1080、420 dpi、字号 1.0；核对认证与关怀人物操作，不能据此推定全部页面均已通过横屏检查。 |
| Android Studio 最终运行 | **成功构建、安装、启动 app** | Android Studio Rabbit 1、JDK 21、Shinian Pixel 9 API 36。IDE Run 显示 `Install successfully finished in 2 s 645 ms`，识别应用进程并启用 Apply Changes；随后同一 APK 完成设备回归。 |

本地材料：[APK 安装包](../releases/拾年-Android-1.0.0-20261021-debug.apk)、[APK 校验信息](../releases/apk-metadata.json)、[18 个页面截图浏览页](../artifacts/android-20261021/review.html)、[主要页面截图目录](../artifacts/android-20261021/validation-screenshots/)、[响应式截图目录](../artifacts/android-20261021/responsive-screenshots/)、[PDF 渲染页目录](../artifacts/android-20261021/pdf-pages/)。主要页面目录含登录、注册、首页、人物选择/新增、家庭胶片、人物页、回忆详情、回忆录封面/故事/PDF、个人与设置、关怀模式及采访页。响应式截图已改为读取实际绘制的 Compose 根节点，已确认关怀人物页内容与按钮可见。


核心回归曾发现检查问题，保留原日志：[滚动修正前](../artifacts/android-20261021/instrumentation-core-before-scroll-fix.log)、[独立接收进程修正前](../artifacts/android-20261021/instrumentation-core-before-probe-fix.log)、[异步等待修正前](../artifacts/android-20261021/instrumentation-core-before-async-wait-fix.log)。最终修正了关怀保存结果页在小屏/大字下的可滚动性，PDF 手势测试等待实际页码变化，并将测试专用接收进程改用独立 Java 实现，避免依赖目标 APK 的 Kotlin 运行时；最终 17 项通过。另修正了异步编辑测试等待条件：等待 HTTP 编辑完成、返回可操作的预览页后，再核对编辑结果。保存 PDF 的目标已由系统新建时，若版本核对或写入失败，客户端会尝试删除本次失败目标，避免留下空 PDF。

另已生成 17 页 A5 中文长文验证 PDF，验证 240 段重复正文与尾段完整保留，目录批注与书签可用；检查中文提取并修正 Android Skia CMap 的康熙部首别名，确保正文可检索、复制；目录链接使用无边框批注，避免导出时出现黑框。封面、目录和正文渲染页见上方 PDF 目录。另有本轮实际三条示例故事生成的 [5 页示例回忆录](../artifacts/android-20261021/拾年-示例回忆录.pdf)，标题与三章正文提取均已核对。

测试及截图使用本机 Android API 36 模拟器。自动化结果证明相应断言和流程已执行；尚需以下人工与设备验收，不将模拟器截图等同于真机结论。

## 独立家庭的真实云端联调

只使用本轮验证脚本新注册的随机账号与独立家庭。账号、令牌和密码未写入本记录；私有文件保存在 Git 忽略的本机验收目录，不作为审核附件或提交内容。未写入原家庭，未退出原家庭的 iOS 会话；没有部署、重启或修改云端服务配置。

主证据为[脱敏云端报告](../artifacts/android-20261021/live-backend-20261020-163149-ab16b7.json)，脚本为 [`verify_live_backend.py`](../scripts/verify_live_backend.py)。报告包含初次失败和恢复重跑，**39 条检查记录中 38 条 passed，存在重复记录；共有 21 个不同检查标签出现过 passed**。原始 `outline_reaches_review` 失败保留，因此 **`all_checks_passed=false`**。恢复后该标签通过来自显式跳过路径，不能覆盖正常回答路径的失败。

| 范围 | 已实际执行的行为 |
| --- | --- |
| 账号与设备会话 | 注册新家庭、登录、`/auth/me` 归属核对、双设备不同令牌；退出第二设备后第一设备仍有效。 |
| 人物 | 新增人物与请求重放、读取、删除额外测试人物；最终保留 1 位虚构验收人物。 |
| 采访与对话 | 开启当前人物会话，骨架暂停/恢复，显式跳过剩余骨架并确认，选择 childhood 模块，过期版本返回 409；真实文本加照片发送，以及相同消息请求 ID 重放不重复。正常回答自动推进质量不计通过，详见下节。 |
| 私有照片 | 同一请求 ID/相同内容上传身份稳定，不同内容复用 ID 返回 409，带会话下载为 JPEG；待保存编辑照片丢弃后下载返回 404。 |
| 草稿 | 真实 AI 草稿生成、读取、人工编辑、revision 更新；旧 revision 确认返回 409，当前 revision 保存，以及重复确认返回同一回忆。 |
| 已保存回忆 | 保留原照片、读取、版本化编辑、旧版本编辑拒绝、时间联动预览；额外测试回忆的旧版本删除拒绝、正确版本删除及后续 404。 |
| 回忆录 | 读取三条故事、上传独立封面、保存设置、同一 request ID 重放版本不增加，过期版本返回 409。 |
| 清理与保留 | 额外删除测试数据已清理；最终保留 1 人、3 条虚构验收回忆与对应照片。最初为 1 条真实 AI 生成回忆及 2 条直接创建的显式虚构 UI 示例，不能将三条都计作 AI 生成。 |

HTTP 调用步骤还记录在同一报告的 `steps` 中；上表描述实际覆盖范围，不把每个 HTTP 请求额外计为一条独立检查。

### 保留的采访失败与云端限制

初轮对 SK04 提供正常虚构回答后，采访重复停留在同一题。继续重复回答使独立测试人物的 `life_interview` 增长至 **20,690,300 bytes**。人物列表完整读取该 JSON 并按创建时间排序，触发 MySQL **1038 / Out of sort memory**，该家庭人物列表返回 503。只读排查确认 `sort_buffer_size=262144`，相同家庭的单个人物、回忆和会话读取仍可成功。证据：[脱敏异常栈与查询](../artifacts/android-20261021/family-list-readonly-diagnosis.txt)、[只读接口诊断](../artifacts/android-20261021/live-read-diagnostics.json)。

经授权，仅通过公开 API 删除这一位可丢弃的测试人物并在同一独立家庭重新创建。没有修改服务端代码、数据库配置或其他家庭。随后使用服务端支持的显式跳过完成剩余骨架，才继续完成对话、照片、草稿、回忆及回忆录功能联调。

因此，本次确认的是客户端可接入既有服务以及上述功能契约；**正常骨架回答的自动推进与内容质量尚未通过，云端大状态导致列表 503 的问题仍保留**。客户端本轮未修复该后端问题。[线上 OpenAPI 摘要](../artifacts/android-20261021/live-contract-summary.json)仅证明实际返回的契约内容，不据其版本号推断完整题库或部署提交。

## 视觉对照用照片

最初上传的 96×72 纯色照片用于验证上传、私有下载、幂等和版本行为。端到端功能流程结束后，仅对上述独立家庭的三条验收回忆替换为仓库已有素材：

| 虚构故事 | 同仓库示例素材 |
| --- | --- |
| 院子里的桂花香 | `DesignPhoto-summer` |
| 第一次远行 | `DesignPhoto-bike` |
| 和家人一起过年 | `DesignPhoto-dinner` |

这些是项目示例图片，**不是真实家庭照片，也不是故事史料**。没有下载新的外部媒体。通过版本化编辑替换故事照片，并同步回忆录封面旧图引用；保留回忆正文、信息字段、采访状态、故事/照片顺序及封面 `x/y/zoom`。三个回忆版本各由 2 更新为 3，回忆录设置版本由 1 更新为 2，最终新照片私有下载均返回 200。

证据：[脱敏照片替换报告](../artifacts/android-20261021/live-credentials-20261020-163149-ab16b7-review-photos.json)、[可选替换脚本](../scripts/prepare_review_photos.py)。脚本默认只验证本地计划，执行时只接受验证器 owner 标记的私有凭据，核对账号/家庭/人物与已知三条回忆，遇版本或内容变化停止。旧图到新图的 ID 映射仅保存在本机 0600 私有状态文件中，本记录不链接该文件。

最后只读核对确认云端仍为新照片及 memoir v2，未被本机旧状态覆盖：[核对报告](../artifacts/android-20261021/review-photos-readonly-current.json)。封面设置或内容改变时先清除旧预览，再用新照片完成绘制，避免短暂显示旧图。

## 原生平台差异与待验项目

- 页面结构、内容与业务操作以现有 iOS 客户端为对照。状态栏、系统返回、键盘、权限、照片/文件选择、保存与分享使用 Android 原生行为，其系统界面和字体栅格效果与 iOS 存在平台差异；最终视觉结论由本轮截图与整体人工审核确认。
- Noto Serif SC 沿用原工程的 OFL 字体文件，[许可随包保存](../app/src/main/res/raw/noto_serif_sc_license.txt)。Android 正文采用系统中文无衬线字体，不分发 Apple PingFang 字体；不能宣称跨平台字形逐像素一致。
- **真机麦克风与普通话识别待验**：尚需在实际 Android 设备检查麦克风授权、拒绝后的恢复提示、系统识别服务可用性及听写结果。模拟器自动化不代替真人讲话与设备识别测试。
- 客户端已通过上表所列验证；真实 UI 已完成独立家庭的整条界面流程。云端正常骨架回答未通过，不能把本次交付写成整个服务质量均已通过。
- 按用户要求进行一次整体人工审核。正式 commit 与 push 尚未进行。

## 审核证据保存说明

`android/artifacts/android-20261021/` 为本机 Git 忽略目录，上述日志、截图及脱敏报告链接仅在保留该目录的本机工作区可用；`android/app/build/reports/` 为构建产物，后续构建可能更新。提交材料时只提供脱敏报告与所需截图，不提交私有凭据、令牌或照片 ID 映射文件。
