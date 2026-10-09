# 阿里云演示环境部署

此配置用于一台 Ubuntu 24.04、2 vCPU、2 GiB 内存的轻量应用服务器。API 只映射到服务器回环地址，MySQL 不映射宿主机端口。公网入口后续由 Nginx 提供 HTTPS。

## 首次启动

```sh
cd /opt/ai-memories/backend
cp .env.production.example .env.production
chmod 600 .env.production
# 编辑 .env.production，填写两个不同的数据库密码和百炼密钥。
docker compose --env-file .env.production -f docker-compose.demo.yml up -d --build
docker compose --env-file .env.production -f docker-compose.demo.yml ps
curl http://127.0.0.1:8000/health
```

API 容器每次启动会先运行 `alembic upgrade head`。Uvicorn 固定为一个 worker，以保持现有进程内并发锁有效。

## 日常查看

```sh
docker compose --env-file .env.production -f docker-compose.demo.yml ps
docker compose --env-file .env.production -f docker-compose.demo.yml logs --tail=100 api
docker stats --no-stream
```

## 更新代码

覆盖源码后重新构建 API：

```sh
docker compose --env-file .env.production -f docker-compose.demo.yml up -d --build api
```

不要删除 `mysql_data` 和 `media_data` 卷。它们分别保存数据库和照片。
