# 拾年项目环境说明

本文件保存项目特有的环境信息；通用执行顺序以 [../SKILL.md](../SKILL.md) 为准。
凭据只记录配置引用，不记录密码、API Key、证书私钥或真实业务数据。

## GitHub

- 仓库根目录：`/Users/student03/Desktop/shinian`
- remote：`origin`
- 远程仓库：`https://github.com/addict-l/shinian-app.git`
- 主分支：`main`
- 后续开发基线：`main`。开始新任务时先查看工作区状态和当前分支，避免混入未完成改动。
- 2026-10-21 核查，当前任务开始时 `main` 为 `d9a68f4`；此前 B03 为 `512915c`，后续基线以实际 Git 日志为准。
- 用户已确定：每个提交块人工审核通过后，正式 commit 并直接推送主分支，不默认创建 PR。

## iOS 前端

- 主线工程：`ios/AIMemoirs.xcodeproj`
- `ios/legacy/` 保留为此前交付与后端联调工程；后续功能默认只修改 `ios/`，除非用户明确指定其他工程。
- Scheme：`AIMemoirs`
- 离线设计样例 Scheme：`AIMemoirs-DesignPreview`，仅用于设计预览，不用于真实云端数据验收。
- 最低支持系统：iOS 18.1
- 项目文档记录的交付工具链：Xcode 26.6
- 默认 API：`https://aimemory.47-82-83-74.nip.io`
- 用户于 2026-10-15 明确指定当前打开的 iPhone 17 Pro / iOS 26.0，UDID `8801F7F7-7154-4AEB-88F2-1E77A8393190`，后续默认复用该设备。此前 Pro / iOS 26.5（`82915145-6254-4561-9028-8F8F8D636B89`）仅是历史设备记录。验证前运行 `xcrun simctl list devices available`，确认名称、系统和状态；使用当前可用 UDID，避免同名设备歧义。
- 复用现有模拟器，不新建或重置模拟器。模拟器不可用时先诊断，确需更换设备时向用户说明。

### iOS 界面方向（用户固定约定）

用户于 2026-10-23 明确要求：后续 iOS UI 仅保证普通字号下的竖屏显示与交互，不再进行最大辅助字号或横屏的专项适配和验收，除非用户之后明确调整。保留字号功能与系统设置；此约定不要求锁定字号、屏幕旋转或更改工程支持方向。

### 关怀模式预览与验证

交付给用户交互检查的 iOS 预览进程不得携带 `-journal.careMode.enabled YES` 或 `-journal.careMode.enabled NO`；模式通过 App 的“设置 → 关怀模式”选择，避免启动参数覆盖设备偏好而导致切换失效。

截图采集中可临时使用上述参数固定模式；结束后必须终止该进程，移除上述参数重新启动，再交付用户操作。模式切换和重启持久化验收也须使用无此参数的启动方式。

建议先从 Xcode 选择 `ios/AIMemoirs.xcodeproj`、`AIMemoirs` Scheme 和现有 iPhone 17 Pro 模拟器，再执行构建和运行。命令行构建可使用 `xcodebuild -project ios/AIMemoirs.xcodeproj -scheme AIMemoirs -configuration Debug -destination 'platform=iOS Simulator,id=8801F7F7-7154-4AEB-88F2-1E77A8393190' build`；具体签名与本机设备状态以 Xcode 实际结果为准。

## Android 前端

- Android Studio 打开 `android/`；源码与测试在 `android/app/`，说明与验收在 `android/docs/`。
- 构建入口：`cd android && ./scripts/build.sh`；本机 JDK 21、SDK API 36，最低 API 26。
- 最新 APK 在 `android/releases/`，截图、日志与受保护验证状态在 `android/artifacts/`（均由 Git 忽略）。
- 现有模拟器：`Shinian_Pixel_9_API_36`，命令行设备以 `adb devices` 为准；复用已有设备。
- 默认 API 与 iOS 相同；共用后端与契约留在 `cloud-deployment/`。

## 阿里云演示环境

项目文档记录的现有服务：

- 云平台：阿里云轻量应用服务器
- 地域：香港
- 操作系统：Ubuntu 24.04 LTS
- 公网地址：`47.82.83.74`
- HTTPS：`https://aimemory.47-82-83-74.nip.io`
- 服务结构：Nginx HTTPS → `127.0.0.1:8000` FastAPI 家庭 Bearer 会话认证 → Docker 内 MySQL 8
- 部署目录：`/opt/ai-memories/backend`
- Compose project name：`backend`
- 部署源码：`cloud-deployment/backend`
- 部署文档：[DEPLOY_ALIYUN.md](../../../../cloud-deployment/backend/DEPLOY_ALIYUN.md)
- 初始搭建历史：[阿里云部署操作记录](../../../../docs/project/operations/initial-aliyun-setup.md)
- 按阶段查部署与验收：[文档总导航](../../../../docs/README.md)

部署访问已确认可用。部署时保留服务器 `.env.production`、认证文件、TLS 配置和数据卷；不把秘密写入 Git。候选验证、备份、健康检查、只读业务检查和回退记录遵循部署文档。GitHub push 不会自动更新云服务器，云端更新必须有单独的部署和验证记录。

健康边界：`/health` 可匿名检查，业务 API 未认证返回 `401` 属于预期；核对 `status`、`database` 后，仍需使用独立测试家庭验证具体业务。

## 项目结构

- `ios/`：当前主线 SwiftUI App
- `ios/legacy/`：此前交付与后端联调工程，使用前先确认任务目标，不要无依据地同时修改两个工程
- `cloud-deployment/backend/`：FastAPI、迁移、Compose 和示例环境
- `cloud-deployment/nginx/`：Nginx 配置示例
- `cloud-deployment/contracts/openapi.json`：接口契约
- `docs/`：需求、任务、验证、部署和交付记录
- 同级 `shinian-validation`：测试源码和验证产物，不属于老师构建，也不上传主仓库

## 验证账号与工具

云端写入验证使用独立测试家庭；不向现有真实家庭写入测试人物、消息、照片或回忆。账号和密码只在执行验证时由用户提供或从受控环境读取，不写入 skill、Git 或日志。

`ios/scripts/make-validation-project.py` 和 `ios/DesignVerification/` 是主线 UI 的验证入口。仓库外的 `shinian-validation/scripts/ios/check.sh` 已调整为 `ios/legacy/`；需要使用该脚本验证主线时，使用等价的 `ios/scripts/make-validation-project.py` 验证命令，不能把 `ios/legacy` 的通过结果当作主线验证结果。

## 2026-10-16 正式家庭账号服务更新

用户已授权并完成正式发布，功能提交 `1f303b7`。现有域名、端口与数据卷不变；业务接口改用 Bearer 设备会话，注册／登录及 `/health` 不再受旧 Basic gate 保护，匿名业务请求仍为 401。正式迁移为 `h10100000001`，3 位家人、12 条回忆、40 份媒体保留。后续部署使用 `/opt/shinian-releases/auth-1f303b7/production-override.json`（含受保护运行配置，不得输出），详情见完整工程 `docs/phase-2/auth-service/deployment.md`。
