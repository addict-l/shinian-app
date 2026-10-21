# 本地文档与验证产物

2026-10-21 起，Android 最新 APK 在 `android/releases/`，截图、日志和私有验证状态统一在 `android/artifacts/`；iOS 新增构建与整理验证产物放在 `ios/artifacts/`。这些目录均由 Git 忽略。既有 `shinian-validation` 历史归档保持原位。各端源码、文档与产物入口见[工程目录说明](directory-layout.md)。


产品仓库保存需求、方案、人工审查材料、简洁验收结论和可读示例。原始逐轮 HTTP 状态、终端日志、截图、测试结果、临时 PDF 与构建缓存保存于同级 `shinian-validation/artifacts/`，不参与 App 构建，也不上传产品 GitHub 仓库。

2026-10-15 整理后的本地归档：

```text
shinian-validation/artifacts/
├── archive/
│   ├── phase-1/logs/                   首轮开发的 315 个历史日志
│   ├── phase-2/childhood-pilot/
│   │   └── raw-documents/              两份完整 HTTP 问答与状态文档
│   ├── project/local-runtime-20261009/  主工程中闲置的 4 个本机运行日志
│   └── document-cleanup-20261015/
│       ├── documents-before.tar.gz     整理前文档备份
│       ├── manifest.json               原路径、目标路径、数量与哈希
│       └── product-source-hashes.json  整理时业务源码的哈希快照
├── logs -> archive/phase-1/logs         兼容旧验证命令与历史链接
├── phase-2-b01/ ... phase-2-b04/         二期各块的原始验证包
├── childhood-backend/                  童年单组验证包
└── childhood-multi/                    童年四组验证包
```

旧日志的兼容链接保留，因此原审查记录里的 `artifacts/logs/...` 仍可在本机打开。现有截图、xcresult、构建缓存和验证包保留原位；这次只整理文档与日志，没有清空验收证据。主工程 `.runtime/logs/` 的四个文件经检查无进程占用后移入归档，数据库、媒体和云端服务均未操作。

两份原始文档为 `childhood-backend-http-qa.md` 和 `childhood-multi-qa.md`。可读问答和草稿继续保存在[童年试点示例](../phase-2/childhood-pilot/README.md)，问题与结论见该试点的验收和多组报告。

本地归档绝对路径可从文件迁移清单查到；老师下载产品仓库时不需要这些目录。后续新增资料放入对应阶段和业务块，原始日志直接写入本地验证目录，历史快照不冒充当前运行结果。
