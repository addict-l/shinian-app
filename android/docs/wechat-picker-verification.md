# 微信式照片选择器

日期：2026-10-21（Asia/Shanghai）。用户提供深色微信相册截图并要求“把选择照片的界面做成微信选择照片这样”。沿用一次整体审核的授权，作为同一 Android 工程的补充，未 commit、未 push。

## 实现与操作

- 深色全屏、四列方形缩略图、2dp 分隔；右下选择圈按用户选择顺序显示编号，支持移除后重排，点击范围 48dp。
- 顶部关闭与相册下拉，可切换全部照片和具体相册；跨相册保留选择，预览返回保留滚动位置。
- 点照片预览当前相册；底部“预览”按顺序查看已选照片。支持左右翻图、双指缩放、双击放大/还原与无障碍放大操作。
- 底部数量与绿色“完成”按钮。零张时禁用；达到上限后继续点选会给出提示。聊天根据已有照片数量补足九张，取消不会加入照片，完成后回到原输入/编辑页面。
- 聊天、回忆编辑、回忆录封面、个人头像与人物照片共用入口；单张用途使用单选。
- Android 8–12 请求旧版图片读取权限，Android 13 请求图片权限，Android 14+ 支持用户仅允许部分照片。恢复前台时重读授权范围，移除不可访问选择；拒绝、部分授权及空图库保留系统选图和设置入口。
- 图片按需载入，缩略缓存最多 12MiB/96 项、三路解码并发；预览最长边不超过 2048px，并修正 EXIF。访问权限异常向 UI 传递，缓存不绕过撤权。

自定义图库只选择照片。上传继续执行现有 JPEG 准备、8MiB 限制和家庭私有媒体接口；没有增加视频上传或承诺服务端保留原始文件。页面没有无效的“原图”控件。

## 审核材料

源文件：`android/app/src/main/java/cn/shinian/app/ui/media/WechatPhotoPicker.kt`、`PhotoPickerLauncher.kt` 和 `media/DevicePhotoLibrary.kt`。

验证时仅向 Android 模拟器插入仓库示例图片，使用独立 UUID 路径，结束后只删除测试插入的 URI。真实上传仍仅使用原有独立虚构验收家庭，没有部署或改动云端服务。

本次接口与页面的模拟器、真实上传和截图结果补充在本记录下方。总体 Android 移植的已有云端正常骨架限制与真机语音待验项仍见 [总验证记录](verification.md)。

## 已执行的检查

| 范围 | 结果与证据 |
| --- | --- |
| 最终构建、JVM、Lint | 构建成功；50 项 JVM 测试通过，0 失败/错误/跳过。Lint 0 Error、92 Warning、1 Hint；见 [构建日志](../artifacts/android-20261021/wechat-picker-build-final.log)。 |
| 原功能回归 | 新选图器接入后的 [27 项整轮记录](../artifacts/android-20261021/wechat-picker-core.log)中，原有 24 项与两项选图测试通过；一项图库测试因重复删除已清理 URI 报错，后续已修复并复验通过。不能将这一轮写作 27 项整轮全绿。 |
| 图库与普通竖屏专项 | [最终 5 项通过](../artifacts/android-20261021/wechat-picker-ui-final.log)：真实 MediaStore 的 pending/trash/排序、缓存与 EXIF/预览尺寸，四列方图、48dp 选择范围、选择顺序与重排、限额、相册过滤、两条预览路径的真实左右滑动、取消不确认；同时复验原输入框与照片管理页。 |
| 实际横屏 | [2 项通过](../artifacts/android-20261021/wechat-picker-landscape-final.log)。测试显式要求 Activity 横屏并核对实际配置，图片为 1616×720、280dpi，约 923×411dp；相册、四列网格、底部按钮和两类预览均实际操作。 |
| 小屏与两倍字号 | [2 项通过](../artifacts/android-20261021/wechat-picker-small-large-font-final.log)，720×1440、320dpi、360dp 宽、字号 2.0。发现小格中心会碰到勾选热区后，将 48dp 热区改为圆形裁剪；保留点击图片预览和点击圆圈选择两种操作，修后完整复验通过。 |
| 拒绝图库权限 | [1 项通过](../artifacts/android-20261021/wechat-picker-denied-final.log)。未授权时不允许完成，备用系统选图入口可见、可操作且不会误确认；之后清除测试权限标记并恢复图片授权。 |
| 独立家庭真实 UI | [1 项通过](../artifacts/android-20261021/wechat-picker-live-app-final.log)，复验登录恢复、人物/回忆、回忆录、关怀切换和聊天可达。 |
| 新选图器到真实上传 | [1 项通过](../artifacts/android-20261021/wechat-picker-live-upload-rendered-final.log)。实际向 MediaStore 插入两张仓库素材，进入生产选图器依次勾选、完成、回到白色输入框、发送双图讲述，核对服务端只有一条本次双图消息，并认证下载、查看及关闭大图。截图等待硬件帧提交后采集，已人工查看实际图片像素。 |

普通竖屏采用 720×1616、280dpi（约 411dp 宽），与原 Pixel 9 验收宽度相同；测试关闭系统动画，覆盖减少动效时的操作。完成后恢复模拟器原分辨率、密度、字号和动画设置。

回归期间保留了两个已关闭的问题：

- 图库测试删除第一张照片后，清理阶段再次删除同一 URI，MediaStore 返回权限异常。测试改为将已删除项移出清理列表，删除后缩略图必须返回空或抛权限异常，不能返回旧缓存。生产权限检查未因此放宽。
- 默认测试调度下，图片 IO 返回与翻页绘制曾触发一次 SnapshotStateObserver 线程异常；更换测试调度器能通过普通竖屏，但横屏出现停顿，因此没有将其作为最终方案。最终统一在主线程发布图库和图片状态，并为 LazyColumn 使用列表滚动 API。原滑动断言保留，普通/横屏复验通过，未关闭硬件绘制或删减预览能力。诊断日志保留在 [首次专项](../artifacts/android-20261021/wechat-picker-final-ui.log)、[调度诊断](../artifacts/android-20261021/wechat-picker-landscape-dispatcher-diagnostic.log)。

## 交付

[更新 APK](../releases/拾年-Android-1.0.1-20261021-debug.apk)、[实际截图浏览页](../artifacts/android-20261021/wechat-picker-review.html)、[照片发送后截图](../artifacts/android-20261021/photo-ui-review.html)、[APK 校验信息](../releases/apk-metadata.json)。截图仅为独立测试家庭与本仓库示例素材，测试插入的媒体 URI 已清理。

本轮通过 Gradle CLI 构建并安装到现有 API 36 模拟器，完成上述实际运行。尝试操作 Android Studio Run 时桌面返回 Mac 锁屏且无法自动解锁，因此未声称本次最终修正版已通过 IDE 按钮启动；Android Studio 工程与安装包均已更新，解锁后可直接 Run。上一轮整体移植的 IDE Run 验证记录仍保留在总记录中。

Android 14+ 部分图库授权分支已实现并按当前授权范围读取；本次实际设备验证包含完整授权与拒绝授权，没有将不同厂商系统弹窗或真机行为计为通过。没有改动或部署云端服务，没有改动 iOS 源码。正式提交与推送等待本轮整体人工审核。
