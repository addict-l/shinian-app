# 拾年（Shinian）

一款帮助家庭记录真实故事的 iOS App：添加家人，通过 AI 对话梳理回忆，附上照片，校对并保存草稿，按人物制作和导出 PDF 回忆录。

**老师运行入口：下载本仓库 `main`，打开 `frontend/AIMemoirs.xcodeproj`，选择 `AIMemoirs` 和 iPhone 模拟器，按 `Command + R`。** 前端默认连接已运行的阿里云后端；无需在 Mac 部署数据库、配置大模型密钥或下载本地测试目录。

## 下载最新版本

在 GitHub 页面选择分支 **main → Code → Download ZIP**，解压后打开 `frontend/AIMemoirs.xcodeproj`。已下载的 ZIP 不会自动更新，需要重新下载。

也可以使用 Git：

```sh
git clone --branch main https://github.com/addict-l/shinian-app.git
cd shinian-app
open frontend/AIMemoirs.xcodeproj
```

已经通过 Git 下载过项目：在原仓库运行 `git pull --ff-only origin main`。可用 `git log -1 --oneline` 查看当前提交；有自己的改动时先保留，避免覆盖。

## 运行条件与步骤

- Mac 和 Xcode；交付验证使用 Xcode 26.6，工程最低支持 iOS 18.1。
- 已安装 iPhone 模拟器运行时；本次验证设备为原 iPhone 17 Pro / iOS 26.5。
- 网络能访问现有阿里云 API。
- 家庭账号 `family`，当前密码由项目维护者单独提供。

1. 打开 `frontend/AIMemoirs.xcodeproj`，等待 Xcode 索引完成。
2. 顶部 Scheme 选择 **AIMemoirs**，设备选择 **iPhone 模拟器**。
3. 按 `Command + R`。模拟器运行无需登录开发者账号或选择开发团队。
4. App 打开后，用 `family` 和单独提供的密码登录。
5. 从“新的回忆”选择或创建家人；“家庭胶片 → 人物头像”可浏览回忆，或制作／继续制作回忆录。

`AIMemoirs-DesignPreview` 是离线设计样例，不用于验证真实云端数据。老师登录现有家庭账号后会看到已有回忆，新增与编辑也保存在同一家庭。

详细试用步骤、问题排查和实际验证范围见 [老师运行与交付指南](docs/t07-delivery.md)。

## 当前功能

- 每位家人一个聊天窗口，恢复最近 20 条消息；当前回忆的分析仍使用完整讲述。
- 信息分析模型与对话模型协作，支持自然引导、就绪判断、明确整理请求和第一人称草稿。
- 一次最多 9 张照片；发送后即时显示文字，失败保留输入和重试状态。照片存储，不送入 AI。
- 草稿校对、确认保存、已保存回忆编辑与删除；创建家人时准备开场白，保存后承接下一篇。
- 每人一本回忆录，封面／内容／整本预览三步制作，三种封面、A5、14／16 pt 字号、目录与连续页码。
- 短篇文字（含标题及时间地点）占内容区半页以内时，首图与文字同页；其余和长文照片继续分页。
- 制作设置自动保存，处理离线待同步和版本冲突，分享前核对故事与设置，导出预览中的 PDF。

长篇草稿整理质量及修改时间后联动标题／正文是 [后续改进](docs/phase-1-tasks.md#后续改进长篇回忆草稿的整理质量)。

## 项目内容与云端版本

```text
frontend/                         可独立运行的 SwiftUI App
  AIMemoirs.xcodeproj              老师打开的工程（仅 App target）
  AIMemoirs/                      业务源码、字体与资源
  Config/Info.plist               云端地址及权限说明
cloud-deployment/
  backend/                        线上对应 FastAPI 源码、依赖、迁移与 Compose
  nginx/                          HTTPS 与家庭认证配置示例
  contracts/openapi.json          前后端接口契约
docs/                             需求、交付、验证和部署记录
```

前端默认 API：`https://aimemory.47-82-83-74.nip.io`。后端使用 FastAPI、MySQL 8、Docker Compose、Nginx HTTPS 和 DashScope，固定单 worker。GitHub 推送不会自动更新云服务器；交付时分别核对运行后端与仓库源码，并记录 [版本清单](docs/delivery-manifest.json)。

GitHub 保留运行和维护所需源码、资源、示例配置、依赖版本及数据库迁移。本地 `shinian-validation` 保存测试源码、验证工程、日志、截图、临时 PDF 和构建缓存，不参与老师构建，也不上传本仓库。生产密码、API 密钥、证书私钥、数据库及真实照片备份保留在受控环境。

## 常见问题

- **没有 iPhone 模拟器：**在 Xcode Settings 的 Components／Platforms 中安装 iOS Simulator Runtime，然后选择模拟器；菜单名称随 Xcode 版本可能不同。
- **提示 Team／provisioning profile：**检查顶部是否误选真机。模拟器不需要开发团队；真机安装需要在 Signing & Capabilities 选择自己的团队和可用 Bundle ID，步骤见交付指南。
- **登录失败：**使用维护者单独提供的当前密码。可在“我的 → 设置”退出后重新登录。
- **无法连接：**在浏览器打开 `https://aimemory.47-82-83-74.nip.io/health`，输入家庭账号。健康响应应显示 `status` 和 `database` 为 `ok`；未认证的 401 属于正常访问限制。
- **无法选择照片：**模拟器相册需要先有图片，可把图片拖入模拟器导入。

## 开发与维护资料

- [前端开发导航](frontend/AIMemoirs/README.md)
- [后端职责](cloud-deployment/backend/README.md)
- [云端部署、备份和回退](cloud-deployment/backend/DEPLOY_ALIYUN.md)
- [T07 已确认交付边界](docs/t07-requirements.md)
- [验证记录](docs/validation-record.md)、[部署记录](docs/cloud-deployment-record.md)

老师自己的 Mac、真机中文语音和实际跨设备体验需要相应环境的人工验收；本机干净下载与模拟器验证不能代替这些实际体验。
