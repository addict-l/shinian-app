# 家庭共享账号服务正式发布记录

2026-10-16 用户明确通过代码审核，授权提交并推送 main，同时授权备份、核对数据后切换正式服务。正式切换时间为 **2026-10-16 21:42:21（Asia/Shanghai）**，后续 HTTPS 和模拟器验收通过。

## 发布版本与运行环境

- 功能提交：`1f303b7e66120618f390629fc5967c3647a6a5ec`，已推送 `origin/main`。
- 运行镜像：`sha256:3b4ac31fab878e1da17514a9787e4fb084a1194ded75a8776f3a29ba5b0d0bef`，标签 `shinian-api:auth-1f303b7`，镜像 revision 标签与功能提交一致。
- 阿里云生产入口：`https://aimemory.47-82-83-74.nip.io`；API 仍只绑定 `127.0.0.1:8000`，MySQL 未开放宿主机端口。
- 迁移：`g10100000001` → `h10100000001`，仅增加账号、设备会话及认证限流表。
- 原账号以原密码绑定到原家庭，未新建替代家庭，也未重置密码。
- Compose project 保持 `backend`，继续使用原数据库及 `backend_media_data` 媒体卷。
- 正式源码目录保留 `/opt/ai-memories/backend`，已覆盖审核提交中的后端源码；原独立部署仓库的 Git 元数据未重写。实际部署版本以镜像 revision 标签、`CLOUD_VERSION.md` 与本记录为准。
- 本次受保护发布目录：`/opt/shinian-releases/auth-1f303b7`。实际运行环境与发布前逐项核对一致，保留原模型及服务配置；密码、令牌和 API Key 未进入 Git、命令参数或验收日志。

## 备份与数据保留

维护窗口先提供 503 与 Retry-After，再停止 API 及后台清理，在停写期间取得数据库、媒体和业务摘要。备份目录：

`/opt/shinian-backups/auth-1f303b7-20261016T133953Z`

目录权限 0700，内容包含 SQL、媒体归档、旧 API 镜像归档、旧源码、生产环境文件、Nginx／原 Basic 认证文件／TLS 配置，以及 SHA256SUMS、迁移前后摘要。SQL 可读取，归档校验及镜像归档目录检查通过；未进行生产数据恢复。

迁移前、绑定原账号后、启动新服务并进行只读核查后三次摘要完全一致，包含全部业务表、关联和删除回执，以及全部媒体文件。保留数据：

| 项目 | 数量 |
| --- | ---: |
| 家庭 | 1 |
| 家庭人物 | 3 |
| 回忆 | 12 |
| 聊天会话 | 41 |
| 聊天消息 | 229 |
| 回忆草稿 | 15 |
| 媒体记录／媒体文件 | 40／40 |
| 回忆录设置 | 1 |
| 回忆人物关联 | 10 |
| 删除回执 | 2 |

iOS 现有界面按仍在家庭中的参与者筛选，显示 10 条珍藏回忆；另两条旧回忆记录及正文仍完整保存在数据库。此展示规则未在本次修改。

## 正式验收

- loopback 与真实 HTTPS 分别验证原账号登录、服务端身份、3 位人物、12 条回忆及关联的 12 张照片，照片响应共 7,723,385 字节，均可正常读取。
- 每次核查使用两个临时设备会话：退出第一个后其请求为 401，第二个仍为 200；核查结束撤销这些临时会话，没有删除业务数据。
- 未登录及旧 Basic 凭据访问业务接口均为 Bearer 401；匿名注册请求可到达后端校验（空表单 422），正式注册入口已开放。未在正式家庭创建测试人物、回忆或测试注册账号；注册成功与跨家庭写入隔离在候选环境完整验收。
- Nginx 移除旧 Basic gate，透传 Bearer，覆盖外部 X-Forwarded-For，并限流登录／注册。保留正式站点现有 ACME 路径、IPv6、证书、TLS 配置和 50M 代理上传上限；配置校验通过后 reload。
- 指定现有 iPhone 17 Pro 更新原 bundle `com.yourname.AIMemoirs.betterui`，不卸载、不重置；普通启动从旧凭据自动登录原家庭，成功后清除旧保存密码，改存设备会话。重新启动继续通过服务端核验并恢复登录。
- 13 个原本机文件的内容摘要全部不变；9 个需迁移的文件已复制到当前账号目录且内容一致，旧文件保留。设置页可见“退出家庭登录”和“仅退出当前设备，家庭和回忆会保留”。
- 审核前独立版本已通过 72 项后端、15 项客户端及 1 项键盘界面测试；详见 [验收记录](verification.md)。

旧版客户端使用 Basic，必须更新后使用本次正式账号服务。此次未执行 App Store 或 TestFlight 发布；指定模拟器已更新并保持原家庭登录。

## 后续维护与回退

生产使用的 Compose override 含受保护运行配置，不得输出其内容或上传 Git。维护时沿用：

```sh
cd /opt/ai-memories/backend
SHINIAN_AUTH_RELEASE=/opt/shinian-releases/auth-1f303b7
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml -f "$SHINIAN_AUTH_RELEASE/production-override.json" ps
```

如需重启相同版本，对上述配置执行 `up -d --no-deps --no-build api`，保留同一数据库、媒体卷、环境与镜像。不要仅凭源码目录中旧 Git HEAD 判断运行版本，也不要重新启用 Basic gate 阻塞注册／登录。

回退先进入维护并停止写入，保存故障时当前数据。受保护发布目录中保留 `nginx.maintenance`、`nginx.original` 和 `rollback-override.json`，备份中保留旧镜像。已有新账号／家庭后，不能直接切回未隔离家庭的旧 API；按 [回退约束](rollout.md#回退) 修复或取得明确数据恢复授权，绝不自动删除新增家庭或执行 downgrade。

## 原始产物

仓库外 `../shinian-validation/artifacts/family-auth-20261016/` 保存发布准备、备份与迁移日志，`production-release-metadata.json`、`production-stopped-manifest.json`、`production-loopback-verification.json`、`production-https-verification.json`、`ios-production-verification.json`，以及本机正式版设置／首页截图。数据库、媒体原件、运行配置和凭据只留在受保护服务器或原应用数据目录。
