# 工程结构

客户端按平台集中存放：iOS 主线位于 `ios/`，第一阶段 iOS 工程保留在 `ios/legacy/`；Android 位于 `android/`。两端通过 HTTPS 调用同一阿里云后端；运行入口以[项目环境](../../.agents/skills/project-development/references/project-environment.md)为准。

```text
shinian/
├── README.md / GLOSSARY.md / AGENTS.md   项目入口、术语、开发约定
├── .agents/skills/project-development/  开发流程及环境说明
├── ios/                                iOS 主线工程、源码、资源与测试
│   ├── AIMemoirs.xcodeproj              Xcode 主线入口
│   ├── legacy/                         第一阶段 iOS 工程
│   └── artifacts/                      本机构建与验证产物（忽略）
├── android/                            Android Studio / Gradle 工程
│   ├── app/                            Kotlin / Compose 源码、资源与测试
│   ├── docs/                           Android 实现与验收文档
│   ├── releases/                       仅保留最新安装包（忽略）
│   └── artifacts/                      本机截图与日志（忽略）
├── cloud-deployment/
│   ├── backend/                         FastAPI、SQLAlchemy、迁移和 Compose
│   ├── nginx/                           HTTPS 与认证配置示例
│   └── contracts/openapi.json           接口契约
└── docs/
    ├── project/                        跨阶段骨架与维护资料
    ├── phase-1/                        T01–T07 需求及交付记录
    └── phase-2/                        新 UI、B01–B05 和童年试点

shinian-validation/                     同级本地验证工程
├── tests/ / scripts/                   测试源码与验证工具
└── artifacts/                          日志、截图、PDF、构建结果及归档
```

运行链路为 SwiftUI / Compose App → Nginx HTTPS → FastAPI 家庭会话认证 → MySQL 与服务器媒体目录；AI 调用由后端发起，PDF 由客户端生成。配置示例随源码交付，真实密码、模型密钥、数据库和照片备份由运行环境保管。

第一阶段资料描述 T01–T07 当时的实现和验证；第二阶段资料记录随后发生的模型、访谈、时间联动和 UI/PDF 优化。旧版的镜像哈希、时延和待办均是当时快照，不能代替当前状态。童年三层采访位于[独立候选试点](../phase-2/childhood-pilot/README.md)，其导出的 Prompt 也放在该试点目录下。
