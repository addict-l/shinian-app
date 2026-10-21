# 整个项目的骨架文档

这些资料跨两次大提交使用，维护当前工程的入口和约定。

| 文档 | 用途 |
| --- | --- |
| [项目首页](../../README.md) | 当前 App 的构建、登录及主要目录 |
| [目录迁移与平台入口](directory-layout.md) | iOS / Android 目录、旧路径与新路径对应关系 |
| [工程结构](architecture.md) | 新旧客户端、云端服务和候选试点的关系 |
| [业务术语](../../GLOSSARY.md) | 项目内概念与命名 |
| [开发约定](../../AGENTS.md) | 进入开发流程的统一入口 |
| [开发流程 skill](../../.agents/skills/project-development/SKILL.md) | 需求、设计、验证、人工审核及提交顺序 |
| [项目环境](../../.agents/skills/project-development/references/project-environment.md) | 当前主线工程、模拟器、Git 和云端环境 |
| [后端说明](../../cloud-deployment/backend/README.md) | 后端模块、运行依赖与配置 |
| [部署、备份与回退手册](../../cloud-deployment/backend/DEPLOY_ALIYUN.md) | 日常维护步骤 |
| [最初阿里云搭建记录](operations/initial-aliyun-setup.md) | 初始基础设施搭建的历史过程 |
| [当前主线客户端说明](../../ios/AIMemoirs/README.md) | 新版客户端的开发导航 |
| [第一阶段客户端说明](../../ios/legacy/AIMemoirs/README.md) | 首轮交付客户端的开发导航 |
| [本地产物规则](local-artifacts.md) | 文档、日志、测试证据的归档位置 |

分阶段需求、计划和验收分别见[第一次大提交](../phase-1/README.md)、[第二次大提交](../phase-2/README.md)。文件迁移对应关系保存在 [document-map.json](document-map.json)。
