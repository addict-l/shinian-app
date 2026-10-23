# 照片接入私有 OSS

## 接入范围与当前状态

照片读取继续使用现有 `/api/v1/media/{id}` 接口，上传与删除沿用各自的原业务接口；后端先校验家庭权限，再操作私有 OSS。媒体 ID、数据库 `file_url` 和客户端接口保持兼容，无需向手机分发 AccessKey，也无需把 Bucket 改为公共读。

本次配置使用 `shinian-media-prod-2026`，中国香港、标准存储、同城冗余 ZRS、私有权限、阻止公共访问和 OSS 托管 AES256 加密。RAM 用户 `shinian-media-backend` 仅具有这个 Bucket 的信息查询、文件列举、上传、读取和删除权限。

2026-10-23 已获授权正式发布 revision `649b5b9`，54 张旧照片已迁入 OSS，并逐张下载核对长度与 SHA-256；本地原件和新图镜像保留。实际运行配置、备份与回退入口见 [本次发布记录](oss-media-deployment-2026-10-23.md)。后续生产变更继续遵循 [部署与回退说明](../../cloud-deployment/backend/DEPLOY_ALIYUN.md)，沿用当前受保护 override、Compose project name、数据库和媒体卷。

## 后端配置

未配置 `MEDIA_STORAGE` 时默认使用本地磁盘。服务端新增以下环境变量；它们需要进入实际 API 容器，不能只写在维护者的 Mac shell 中。

```dotenv
MEDIA_STORAGE=oss
OSS_BUCKET=shinian-media-prod-2026
OSS_REGION=cn-hongkong
OSS_ENDPOINT=https://oss-cn-hongkong-internal.aliyuncs.com
OSS_PREFIX=media/
OSS_LOCAL_FALLBACK=true
OSS_LOCAL_MIRROR=true
OSS_CREDENTIALS_FILE=/run/secrets/shinian-oss.env
```

- `MEDIA_ROOT` 继续使用原照片卷 `/data/media`。`OSS_PREFIX` 在迁移前确定，切换期间不要变更。
- 同地域香港服务器使用上面的 HTTPS 内网 Endpoint。在 Mac 或不具备阿里云同地域内网连接的候选环境验证时，显式改用 `https://oss-cn-hongkong.aliyuncs.com`。内网无法连接时按存储错误处理，不自动尝试其他地址。
- `OSS_LOCAL_FALLBACK=true` 仅在 OSS 明确返回对象 `NoSuchKey` 时读取旧本地照片；权限不足、Bucket 不存在、网络错误和服务异常不会读取本地掩盖故障。
- `OSS_LOCAL_MIRROR=true` 让新照片在 OSS 上传成功后保留本地镜像，便于过渡期间回退。镜像写入失败时本次上传失败，不能把缺少本地副本的照片报告成完整成功。会继续占用原照片卷，需保留磁盘空间。
- 应用删除照片时清理相应 OSS 对象和活动本地副本；独立备份按既有备份策略保留。应用照片删除仍需家庭权限验证。
- OSS 模式下删除先提交数据库和持久清理任务，已删除照片立即无法通过接口访问；后台任务每 15 秒检查队列，失败时保留任务供后续重试。业务请求不等待历史 OSS 清理任务，以免网络异常拖慢编辑或删除。

`OSS_CREDENTIALS_FILE` 是容器内的受保护 dotenv 文件，文件内容仅有真实 RAM 密钥，示例格式为：

```dotenv
OSS_ACCESS_KEY_ID=在受保护文件中填写
OSS_ACCESS_KEY_SECRET=在受保护文件中填写
```

在服务器上把文件保存在 Git 工作区外，所有者只允许维护者或服务账号，权限 `0600`；使用只读 bind mount 或 Docker secrets 映射到上面的容器路径。不要把 RAM 导出的 CSV、真实 dotenv、签名 URL 或密钥写入 Git、命令行参数、工单和验证报告。下载 CSV 不能直接作为 dotenv 使用。

也可由部署平台向容器直接注入 `OSS_ACCESS_KEY_ID` 与 `OSS_ACCESS_KEY_SECRET`；显式环境变量优先于凭据文件。配置文件内容不得输出。不要使用 `docker compose config` 的完整展开输出或 `docker inspect` 的完整环境输出作验收材料。

## 验证与发布顺序

1. 本地以临时目录和隔离数据库验证磁盘/OSS 行为；测试仅用模拟对象存储或独立测试对象。
2. 在隔离候选环境使用独立测试家庭验证上传、读取、删除、跨家庭拒绝访问、OSS 故障返回及本地镜像。不向真实家庭写入验证照片。
3. 经授权后，在维护窗口备份配套数据库、媒体卷和运行配置，记录旧镜像、源码版本和媒体清单。检查备份可读取。
4. 在配置好 OSS 凭据的候选运行环境执行下面的 dry-run，审核 JSON。必要时暂停照片写入，以取得可核对的最终快照。
5. 真实照片迁移获授权后显式使用 `--apply`，逐项核对远端下载后的长度与 SHA-256，再重复 dry-run。两次过程均不删除本地文件、不修改媒体 ID 或 `file_url`。
6. 配套候选验证和人工审核通过、正式发布获授权后，将 API 的 `MEDIA_STORAGE` 切换为 `oss`。保留本地回退和镜像，重建 API 容器后检查健康及实际照片业务。

## 旧照片迁移工具

运行入口为 `cloud-deployment/backend/scripts/migrate_media_to_oss.py`。以下命令在已安装候选依赖、数据库和照片卷均指向待核对环境的 **backend 运行环境内部**执行。命令本身不负责选择或部署到服务器，不会更改正在运行 API 的环境。

```sh
umask 077
MEDIA_STORAGE=oss python scripts/migrate_media_to_oss.py > /受保护目录/oss-dry-run.json
```

默认 dry-run 读取本地 JPEG、查询并真实下载已有远端对象进行比对；缺少的对象仅报告 `would_copy`，不上传。它需要网络和读取权限，但不执行 OSS 写入。

明确获准执行真实迁移后：

```sh
MEDIA_STORAGE=oss python scripts/migrate_media_to_oss.py --apply > /受保护目录/oss-apply.json
MEDIA_STORAGE=oss python scripts/migrate_media_to_oss.py > /受保护目录/oss-after.json
```

脚本使用 `MEDIA_ROOT` 或 backend 默认媒体目录。需要映射目录时可用 `--media-root /实际挂载目录`；目录必须已存在。未配置 `MEDIA_STORAGE=oss` 会失败退出，避免把磁盘自校验当成 OSS 迁移成功。

脚本从数据库快照读取 `MediaAssetModel` 中 `type=image` 的 ID，不扫描所有 `.jpg`，因此不会把已删除或孤立文件重新上传。每个 ID 在独立事务中通过 `SELECT ... FOR UPDATE` 重新检查，并在读取、上传和校验完成后释放行锁；并发删除会与此事务协调。快照后新产生的照片需在下一次幂等运行中复查。最终验收建议短暂停止照片写入，不要在数据库和照片持续变化时声称取得一致备份。

校验使用实际本地 `.jpg` 字节的长度及 SHA-256，并下载 OSS 原对象计算相同指标。数据库 `content_hash` 记录的是上传前文件的哈希，不能用于校验服务端压缩、转正后的 JPEG；OSS metadata、ETag 或应用的本地 fallback 也不能代替远端下载校验。

| JSON 状态 | 含义与处理 |
|---|---|
| `would_copy` | dry-run 时本地存在、远端不存在；明确应用后才能复制 |
| `copied_and_verified` | 本次新建对象，真实下载后长度和 SHA-256 均与本地一致 |
| `already_verified` | 对象已存在且下载后与本地一致；安全跳过，重复运行不会覆盖 |
| `verified_remote_only` | 本地缺失、远端可下载；仅验证远端可读，**没有完成本地一致性比对**，需要单独核对本地回退条件 |
| `skipped_deleted` / `skipped_non_image` | 快照后记录被删或类型改变，跳过且不上传 |
| `conflict` | 同一 ID 的远端内容与本地不一致，保留原对象并报告失败，人工调查后处理 |
| `missing_both` | 本地与远端均缺失，报告失败并从独立备份调查 |
| `storage_error` | 存储、权限、数据库或校验读取失败；记录异常类型，原始异常和秘密不输出 |

创建对象使用 OSS 服务端禁止覆盖条件，即使存在绕过数据库锁的外部写入，也不会覆盖同名对象。若竞争写入已创建对象，脚本重新下载比对；内容一致才记为已验证，否则记为冲突。校验失败不会删除远端或本地内容。

报告含 `schema_version`、运行模式、数据库快照照片数、各状态计数、`error_count` 和逐 ID 的指纹；退出码为 `0` 表示无错误，非 `0` 表示需要处理错误。报告可能包含媒体 ID 与照片指纹，和备份一样保存在受保护目录。报告没有任何家庭姓名、原始图片内容、密钥或原始 SDK 错误。

迁移完成的审核条件为：无 `would_copy`、`conflict`、`missing_both` 或 `storage_error`，快照中的实际照片均已校验或有明确的跳过说明；`verified_remote_only` 必须单独说明其本地副本缺失，不能作为“所有照片本地副本完整”的证据。

## 过渡与回退

本次迁移工具始终保留原本地 JPEG、原始数据库 ID 和接口 URL；新照片保留 OSS 与本地镜像。不要在迁移完成后立即删除本地卷，也不要把同城冗余当作误删除备份。

需要回退时，先暂停照片写入、保留故障版本当前数据，并核对所有仍在数据库中的照片是否具有本地副本，尤其是 `verified_remote_only` 项。存在缺失时先从独立备份或经验证的 OSS 对象恢复本地副本，再切换回本地；本工具不会自动回填这些缺失文件。

按部署记录恢复旧镜像及配套受保护配置，将 `MEDIA_STORAGE=local`，保留同一数据库和媒体卷，再检查照片读取、上传、删除及家庭访问控制。不自动恢复数据库快照、不执行数据库 downgrade、不删除 OSS 对象。若过渡中关闭过本地镜像，必须先将此后新增的 OSS 照片复制并验证回本地，再使用本地模式。

在迁移审核、恢复演练和正式运行观察完成前，保持 `OSS_LOCAL_MIRROR=true`。清理本地历史副本、停用镜像或改生命周期应作为后续独立操作评估与授权。
