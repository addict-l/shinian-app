# 拾年（Shinian）

“拾年”是一款用于家庭共同记录与整理回忆的 iOS 应用。用户可以添加家庭成员，通过 AI 对话梳理故事，预览并保存回忆，再从首页、回忆列表和家庭胶片中浏览这些内容。

本仓库按运行环境分成两部分：

```text
shinian/
├── frontend/                    iOS 前端工程
│   ├── AIMemoirs.xcodeproj      Xcode 工程入口
│   ├── AIMemoirs/               SwiftUI 应用源码与资源
│   ├── AIMemoirsTests/          单元与集成测试
│   ├── AIMemoirsUITests/        UI 自动化测试
│   ├── Config/Info.plist        应用名称、权限和 API 地址
│   └── scripts/                 前端检查脚本
├── cloud-deployment/            云端 API、数据库迁移与部署资料
│   ├── backend/                 FastAPI 后端、Docker 配置和测试
│   ├── contracts/openapi.json   前后端接口契约
│   ├── 阿里云部署操作记录.md      服务器部署过程与维护说明
│   └── ai-memories-backend-deploy.tar.gz
└── README.md
```

## 系统架构

```text
iOS App（SwiftUI）
    │  HTTPS + HTTP Basic Authentication
    ▼
Nginx（TLS、访问认证、反向代理）
    │  127.0.0.1:8000
    ▼
FastAPI（业务接口、AI 对话、数据处理）
    ├── MySQL 8.0（家庭成员、会话、回忆等结构化数据）
    ├── 服务端媒体目录（回忆照片）
    └── DashScope 兼容接口（AI 对话与回忆整理）
```

前端采用 SwiftUI。`AIMemoirs/App` 负责应用入口和导航，`Features` 按业务页面拆分，`Shared` 存放设计系统、通用组件和共享状态，`Models` 保存业务模型，`Networking` 负责请求云端 API。登录凭据保存在设备系统钥匙串中；iOS 模拟器使用本机调试存储。

云端采用 Nginx、FastAPI、MySQL 和 Docker Compose。Nginx 对外提供 HTTPS 和家庭账号认证，再把请求转发到只监听服务器回环地址的 FastAPI。后端负责数据库读写、媒体存储和 AI 服务调用。云端部署默认已经持续运行，普通前端开发不需要在 Mac 上启动后端。

## 前端运行环境

- 一台 Mac
- Xcode 26 或兼容当前工程格式的较新版本
- iOS 18.1 或更高版本的模拟器，也可以使用满足该版本要求的真机
- 可访问互联网，以连接已部署的云端 API
- 有效的家庭账号和密码；账号默认是 `family`，密码由项目维护者提供

API 地址已经写入 `frontend/Config/Info.plist`：

```text
https://aimemory.47-82-83-74.nip.io
```

## 启动前端

1. 在 Finder 中进入 `frontend`，双击 `AIMemoirs.xcodeproj`。
2. 等待 Xcode 完成工程索引。
3. 在 Xcode 顶部选择 `AIMemoirs` Scheme。
4. 选择一个 iOS 18.1 或更高版本的 iPhone 模拟器。
5. 点击运行按钮，或按 `Command + R`。
6. App 打开后，使用家庭账号 `family` 和维护者提供的当前密码登录。

首次运行时，macOS 可能会询问是否允许 Xcode、模拟器或应用访问网络；允许后即可连接云端。登录密码不要写入源码、README 或提交记录。

## 常见问题

### Xcode 打开后没有可运行设备

打开 Xcode 的 **Settings → Platforms**，安装一个 iOS 18.1 或更高版本的 Simulator Runtime，然后重新选择模拟器。

### App 显示登录失效

服务器上的家庭密码可能已经更新。进入 App 的“我的 → 设置”，退出家庭账号，再使用新密码登录。如果无法进入设置，可以删除模拟器中的 App 后重新运行工程。

### App 无法连接服务器

先在 Mac 浏览器访问：

```text
https://aimemory.47-82-83-74.nip.io/health
```

浏览器要求输入账号和密码属于正常现象。能够登录并看到包含 `"status":"ok"` 的响应，说明云端可用；否则请联系云服务器维护者检查 Nginx、API 容器和数据库容器。

### 需要更换云端地址

修改 `frontend/Config/Info.plist` 中的 `AI_MEMORIES_API_URL`，保持 HTTPS 地址不带末尾斜杠，然后重新构建 App。

## 开发导航

- 前端目录职责和开发约定：`frontend/AIMemoirs/README.md`
- 后端服务说明：`cloud-deployment/backend/README.md`
- 阿里云部署与维护记录：`cloud-deployment/阿里云部署操作记录.md`
- OpenAPI 契约：`cloud-deployment/contracts/openapi.json`

如只需运行 iOS 客户端，按照“启动前端”操作即可，无需执行 `cloud-deployment` 中的命令。
