# 云端部署、备份和回退

> 2026-10-16 更新：正式服务已改为家庭账号注册及 Bearer 设备会话。下文 Basic Authentication 为历史部署说明，当前认证、受保护的 Compose override、备份及回退方式以[家庭账号正式发布记录](../../docs/phase-2/auth-service/deployment.md)为准。旧客户端须更新，不能在新服务前重新启用 Basic gate。

老师运行前端直接连接现有阿里云，不需要执行本页。以下供维护者在自己的 Ubuntu 24.04 服务器部署或维护同版本后端；生产配置、密码、证书及业务备份不放入 Git。

## 运行结构

Docker Compose 运行 MySQL 8 和单 worker FastAPI；MySQL 无宿主机端口，API 仅绑定 127.0.0.1:8000，公网经 Nginx 提供 HTTPS 和家庭 Basic Authentication。数据卷为 mysql_data、media_data，具体 Docker 卷名取决于 Compose project name。现有服务器目录为 /opt/ai-memories/backend，其 Compose project name 为 backend。

完整源码位于本仓库 cloud-deployment/backend；复制到独立服务器目录时保持 Compose project name 一致，避免意外创建新的空卷。依赖在 requirements.txt 固定，数据库迁移随代码交付。最新迁移 f10100000001；启动容器先执行 alembic upgrade head，再启动单 worker API。

## 新服务器首次部署

1. 安装 Docker Engine、Compose plugin 和 Nginx；取得自己域名的 TLS 证书。
2. 将本仓库 cloud-deployment/backend 完整复制到 /opt/ai-memories/backend（不覆盖已有生产配置）。
3. 复制 .env.production.example 为 .env.production，填写两个不同的强数据库密码、自己的 DashScope 密钥、模型、HTTPS 主机名。数据库密码须使用 URL 安全的字母数字，因为 Compose 将其用于 DATABASE_URL。chmod 600 .env.production。
4. 启动内部服务并检查健康：

```sh
cd /opt/ai-memories/backend
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml config --quiet
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml up -d --build
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml ps
curl --fail http://127.0.0.1:8000/health
```

5. 使用交付的 nginx/aimemory.conf.example 作为结构参考，填写自己的域名和证书路径。用 htpasswd 交互式创建家庭认证文件（不将密码放进命令行或 Git），赋予 Nginx 读取权限；执行 nginx -t 后再重新加载。公网只开放需要的 SSH、80 和 443，内部 8000 及 MySQL 不开放。
6. 修改前端 Config/Info.plist 的 AI_MEMORIES_API_URL 指向自己的 HTTPS 地址，再重新构建。现有前端默认指向当前阿里云，不能把部署新空服务器当作已复制家庭数据。

新数据库默认为空。App 首次创建家庭及人物，图片和回忆通过正常流程保存；要迁移已有业务，必须同时恢复对应数据库与媒体，不只复制源码。

API 使用进程内会话锁，保持 workers=1；扩容前需改用跨进程锁并验证。照片格式和容量限制由 API 校验，Nginx 的上传上限略高于单图 8 MB。AI 调用可能需要等待，代理读取超时与现有对话流程相匹配。

## 发布前备份

在维护窗口执行，备份目录只对维护者可读。不要在用户持续写入时把不同时间的数据库与照片快照当作一致备份；需要恢复时先核对快照时间和业务写入情况。

```sh
cd /opt/ai-memories/backend
umask 077
SHINIAN_BACKUP=/opt/shinian-backups/$(date +%Y%m%d-%H%M%S)
mkdir -p "$SHINIAN_BACKUP"
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml ps -q api > "$SHINIAN_BACKUP/api-container"
docker inspect -f '{{.Image}}' "$(cat "$SHINIAN_BACKUP/api-container")" > "$SHINIAN_BACKUP/api-image"
git rev-parse HEAD > "$SHINIAN_BACKUP/source-revision"
cp .env.production "$SHINIAN_BACKUP/env.production"
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml exec -T db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces ai_memories' > "$SHINIAN_BACKUP/database.sql"
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml exec -T api tar -C /data/media -czf - . > "$SHINIAN_BACKUP/media.tar.gz"
tar --exclude=.git --exclude=.env.production --exclude=.venv --exclude=__pycache__ -czf "$SHINIAN_BACKUP/backend-source.tar.gz" .
```

同时备份实际 Nginx 配置、家庭认证文件和 TLS 配置到受控目录；不导出到 GitHub。保留旧镜像标识或离线镜像包。检查备份可读取和包含相应数据后再更新源码。

## 更新与验证

从已审核 GitHub 提交复制后端源码到当前目录，保留 .env.production、认证文件和数据卷。先在隔离测试库验证候选，再更新 API：

```sh
cd /opt/ai-memories/backend
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml up -d --build api
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml ps
curl --fail http://127.0.0.1:8000/health
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml exec -T api alembic current
```

还需通过 HTTPS 家庭登录只读核对人物、聊天窗口、回忆、照片和回忆录快照；功能验收在隔离数据上完成。数据库迁移成功或健康通过不能代替整个流程。正式家庭库不执行测试清理，示例／测试数据不写入现有家庭。部署目录、Git 提交、运行镜像与源码哈希分别记录于 [部署记录](../../docs/cloud-deployment-record.md)。GitHub push 不会自动更新当前云服务器。

## 回退

应用回退先保留故障版本当前数据，再使用记录的旧镜像与配套源码／配置启动 API；不删除数据卷、不自动执行 alembic downgrade。现有迁移为兼容性增量，旧镜像能否读取新数据需根据对应发布记录核对。

可在受控临时 Compose override 文件中为 api 指定已记录的旧镜像，再执行 up -d --no-build api；显式保留相同 project name、端口、媒体卷和环境文件，随后检查健康与业务只读接口。不要仅 git reset 后以为正在运行的容器也已回退。

若确需恢复数据库和媒体快照，应停写，先额外备份当前状态，再在隔离环境演练对应 SQL 与媒体恢复，确认后人工执行。恢复会影响备份后的业务记录，不能把代码回退与业务数据恢复混为一步。

## 已执行与未执行

现有 T06 迁移及镜像已经部署并验证。本次 T07 主要交付整理，后端业务源码没有变化，因此不为文档与示例配置重启正式 API或重复运行迁移。实际结果、当前运行镜像、验证范围和源文件映射见 [版本清单](../../docs/delivery-manifest.json) 和 [老师指南](../../docs/t07-delivery.md)。本页首次部署与数据恢复步骤是维护说明，不宣称本次重新部署新服务器或演练恢复。
