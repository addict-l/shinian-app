# 自有域名 HTTPS 与 Android 接入（2026-10-24）

## 当前入口

- 自有域名：`https://api.奶娃回忆录.club`，配置和客户端使用其Punycode形式 `https://api.xn--zbs33ddmy9oeqa.club`。
- DNS：`api` 的 A 记录指向现有阿里云香港服务器 `47.82.83.74`。
- 原入口 `https://aimemory.47-82-83-74.nip.io` 继续服务现有客户端。两个入口使用同一后端、家庭、数据库和媒体，没有新建业务数据卷。
- 用户已明确授权新HTTPS入口的上线；Android1.0.2切换新入口，iOS当前入口保持原配置。

## 诊断与修复依据

华为HarmonyOS／卓易通／中国移动的实际报告显示，原入口的DNS返回正确IPv4，DIRECT TCP连接后在TLS阶段发生 `SocketException / connection_reset`。固定IPv4未避开TLS失败，默认TLS／仅TLS1.2／默认TLS的三次对照也都失败。证据只定位到该连接路径，不能判定重置由运营商、源站还是其他设备发出。

新域名已启用受信任证书。用户在同一手机、只用移动数据打开新HTTPS健康地址，明确确认 `status=ok`、`database=ok` 且无证书警告。此结果验证浏览器访问路径；App原始登录与业务验收以新版实体机测试为准。

## 服务器配置

- 配置示例：[shinian-owned-domain.conf.example](../../cloud-deployment/nginx/shinian-owned-domain.conf.example)，实际独立站点为 `/etc/nginx/sites-available/shinian-api-idn`，由同名sites-enabled链接启用。
- 新站点严格校验外部Host为新域名，转发至原 `127.0.0.1:8000` 时使用后端已允许的canonical Host。Bearer认证头、限流、上传上限和代理超时保持原服务规则；相对媒体路径继续通过当前客户端入口读取。
- 以上网关规则适配后端已有TrustedHost名单，未重启API或放宽后端Host验证。新入口的错误Host负例返回400，匿名 `/api/v1/auth/me` 返回401。
- 原Nginx站点配置SHA256及后端容器ID在上线前后保持。操作未迁移数据库或写入真实家庭数据。

## 证书与续期

- 证书名：`shinian-api-idn`，SAN为 `api.xn--zbs33ddmy9oeqa.club`。
- 签发者：Let's Encrypt YE2；本次证书有效至2027-01-22。私钥仅存服务器 `/etc/letsencrypt/`，不进入Git或本机交付物。
- HTTP-01 webroot：`/var/www/html`，公开验证目录 `.well-known/acme-challenge` 为755。
- 复用现有已启用的 `certbot.timer`。续期重载命令为 `nginx -t && systemctl reload nginx`；Certbot2.9在renewal配置中使用 `renew_hook` 字段保存该deploy-hook。
- 隔离staging验证、正式签发、证书链／域名校验、`renew --dry-run --run-deploy-hooks` 均通过。首次正式签发遇到secondary DNS SERVFAIL，核对权威和公共DNS正常后受控重试成功。

## 备份与回退

- 受控备份：服务器 `/opt/shinian-backups/idn-https-20261024-d7c017`；配置、证书及操作日志只留在服务器受保护目录。
- 本次release记录：`/opt/shinian-releases/idn-https-20261024-d7c017`。
- 回退撤下本次新增的sites-enabled链接，`nginx -t`后reload，复查原入口健康200及匿名接口401。保留后端容器和数据卷；清理新证书前核对没有已启用配置引用。

## Android交付

版本1.0.2／versionCode3使用新地址，保持应用ID和原签名，以覆盖安装。会话按服务器隔离，因此升级后需要使用原家庭账号重新登录；不把旧域名绑定的令牌自动发送到新域名。

构建、测试、签名及APK哈希以 `android/releases/apk-metadata.json` 和本机 `android/artifacts/connectivity-20261024/product-release/` 的本次结果为准。该记录不替代用户实体机最终验收。

## 2026-10-25 云端与 GitHub 同步标记

本次同步提交标注为“接入自有域名 HTTPS，Android 1.0.2 切换新入口”。本节所在的 `main` 提交为本次源码版本；云端 `/opt/ai-memories/backend/CLOUD_VERSION.md` 的自有域名同步章节，以及本次发布目录的 `SYNC_VERSION.json` 记录实际提交号、源码树、APK哈希和核对结果。

同步范围包括Android版本与API配置、域名Nginx配置示例、接入和环境记录；云端另存该提交的干净源码快照、安装包与校验清单。发布目录按 `owned-domain-android-1.0.2-20261025-<提交前缀>` 命名。APK及受控部署材料继续按工程产物规则归档，不将二进制、私钥、API密钥或真实家庭数据写入Git。

- Android：`cn.shinian.app`，1.0.2／versionCode3，原签名可覆盖安装。
- APK：`拾年-Android-1.0.2-20261024-debug.apk`，40,072,618字节；SHA-256为 `4baa5df633ff5fe6fba5df91f5106fa4f794b80ef71cb6a2e5d8e3bdd4a6d15f`。
- 新API：`https://api.xn--zbs33ddmy9oeqa.club`。
- 已运行验证：50项JVM测试、lint、现有Android模拟器上实际产品客户端的注册／登录／家庭数据读取／会话撤销联调。
- 云端后端：运行镜像仍为 `shinian-api:sort-a1ecee6-20261023`，revision为 `a1ecee61eae633898f1ba3a7200a630ca66a32c2`。本次未修改后端业务代码；受控发布源码和运行容器内265个受版本控制的后端文件逐一SHA-256匹配。该运行revision与包含Android／文档变化的仓库HEAD不同，并不表示后端代码落后。
- 云端Nginx有效指令与本次配置示例一致；同步归档时会统一注释，使文件字节也能直接核对。
- 历史部署目录 `/opt/ai-memories/backend` 的Git HEAD不作为当前运行版本依据。使用本次同步清单、实际镜像revision、源码哈希与受保护override追踪运行状态。
- 本地另有此前采访优化等未提交内容，不属于本次提交或云端源码快照。

验收边界：用户已确认同一华为手机的移动数据浏览器访问新域名正常且无证书警告；新版App的原账号登录、聊天和照片实体机结果尚未回传。本次同步按用户明确的发布指令执行，不把浏览器检查或模拟器联调标记为完整实体机业务验收。
