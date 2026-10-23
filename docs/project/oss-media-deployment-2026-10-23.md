# OSS 照片存储正式发布记录

2026-10-23 用户明确通过 OSS 接入与迁移工具审核，授权推送并同步最新后端。正式 HTTPS 于 **2026-10-23 15:47:52（Asia/Shanghai）** 恢复，生产已启用私有 OSS；数据库和本地照片卷保留。

## 版本与配置

- OSS 功能提交：`532d930`；迁移工具与说明：`9ae6f42`。
- 正式运行 revision：`649b5b900244fd3742f3226f8e2b6d9d07387992`，已推送 GitHub `main`。
- 基于此前线上 `770f841` 保留完整 v3j/v4d 采访历史，同时合并远端 `e627f38` 的 iOS 更新；OSS 审核通过的 10 份文件内容未改变。
- 镜像：`shinian-api:oss-649b5b9-20261023`，ID `sha256:e32bf48e6a7e288ad64c9f61ce6cd7510284cab34b3bd50d1f8491fcc0c9df96`；257 份部署源码逐字节与已测版本一致。
- 生产入口仍为 `https://aimemory.47-82-83-74.nip.io`，API 仅绑定 `127.0.0.1:8000`。Compose project 保持 `backend`，沿用原数据库、网络与 `backend_media_data`；MySQL 未重建、未暴露端口。
- 数据库仍为 `h10100000001`，本次没有新增数据库迁移。
- `MEDIA_STORAGE=oss`；Bucket 为 `shinian-media-prod-2026`，中国香港、标准同城冗余、私有并阻止公共访问；使用 HTTPS 内网 Endpoint 和正式 `media/` 前缀。
- `OSS_LOCAL_MIRROR=true`、`OSS_LOCAL_FALLBACK=true`。原采访开关、两套 runtime 目录及 pin、模型与其他运行环境完整保留。
- RAM 密钥以受保护文件只读挂载，未进入 Git、命令参数或公开日志；客户端仍通过原带家庭鉴权的媒体接口读取。

正式发布目录：`/opt/shinian-releases/oss-649b5b9-20261023`。权威后端源码位于其 `source/backend/`，实际受保护运行配置为其 `production-override.json`；源码目录的 Git HEAD 不能代替镜像 revision。`/opt/ai-memories/backend/CLOUD_VERSION.md` 已记录这些引用。

## 验证

新后端基线的 132 项去重测试通过：36 项存储与迁移、51 项采访离线回归、45 项隔离 MySQL API 回归（含新采访与照片边界）。云端另外复查两项骨架持久化顺序修复，属于上述 51 项，不重复计数。

指定 iPhone 17 Pro / iOS 26.0 的隔离 App 已与整合候选完成真实 OSS 照片缩略图和大图预览。正式环境默认 App 已恢复原有登录及家庭、回忆、聊天读取；在默认进程单独运行期间，确认 App 客户端媒体 GET `200` 共 6 次，头像图片可见。本轮未完成既有照片详情的视觉确认，不将其记录为生产照片详情界面验收通过；生产照片另有下面逐张远程下载校验结果。未重装 App 或修改真实家庭数据、代码及输入设置。

正式切换后的 loopback 与真实 HTTPS 健康检查均为 `status=ok`、`database=ok`、`llm_configured=true`；匿名业务请求返回预期的 `401`。全部 257 份运行源码匹配清单，原数据库容器、数据库版本及媒体卷保持一致。

## 备份与迁移

先归档旧 `770f841` 镜像、源码及完整受保护配置；维护时通过 Nginx 暂停写入，停止 API 及其后台清理，再取得一致 SQL、媒体及业务摘要。API 停止于 15:45:24，HTTPS 恢复于 15:47:52，约 2 分 28 秒。

- 旧镜像与配置：`/opt/shinian-backups/oss-prestage-20261023T073407Z`。
- 停写一致备份：`/opt/shinian-backups/oss-649b5b9-20261023T074516Z`。
- 备份目录权限 `0700`、文件 `0600`。SQL 可读取，归档及 SHA 校验通过；媒体归档逐文件字节与停写原件一致。

停写快照为 **54 条图片记录、54 个 JPEG，共 25,014,187 字节**。迁移临时容器以只读方式挂载原媒体卷，结果如下：

| 阶段 | 结果 |
| --- | --- |
| 预览 | `would_copy=54`，未上传 |
| 应用 | `copied_and_verified=54`，错误 0 |
| 再次预览 | `already_verified=54`，错误 0 |
| 新生产容器复核 | 54 张均再次真实下载并与本地长度、SHA-256 一致 |

业务表摘要与全部本地文件字节在备份、迁移和启动后保持一致。没有删除本地原件、修改媒体 ID/URL、向真实家庭写测试照片或恢复数据库。新照片继续保留本地镜像供过渡与回退，因此本地磁盘仍会占用相应空间。

## 后续维护与回退

后续重建 API 应沿用本次实际 override，先核对其与当前运行版本一致：

```sh
cd /opt/ai-memories/backend
SHINIAN_OSS_RELEASE=/opt/shinian-releases/oss-649b5b9-20261023
docker compose --project-name backend --env-file .env.production -f docker-compose.demo.yml -f "$SHINIAN_OSS_RELEASE/production-override.json" ps
```

本次已准备受保护回退脚本 `/opt/shinian-releases/oss-649b5b9-20261023/rollback.py`，其固定恢复已备份的 `770f841` API 镜像、完整运行环境及原 Nginx；保留相同数据库和媒体卷。本次未执行回退。实际使用前先暂停写入并保留故障时数据，核对所有现存图片仍有本地副本；该脚本不执行数据库恢复、downgrade 或 OSS 删除。实际回退后须将 `CLOUD_VERSION.md` 与发布记录同步为回退后的实际镜像和 revision；脚本不自动更新这些记录。

清理本地副本、关闭镜像、修改生命周期属于后续独立操作。配置、迁移和校验规则见 [OSS 接入说明](oss-media-storage.md)。原始业务快照、逐图片指纹和凭据仅存受保护服务器；本机脱敏发布材料位于仓库外验证目录，不上传业务原件。
