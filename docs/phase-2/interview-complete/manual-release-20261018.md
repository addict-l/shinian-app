# v1.29真实后端人工测试发布

用户最新直接授权当前版本和新题库上线，供其人工测试。已于2026-10-18 14:04:11（Asia/Shanghai）切换真实后端；质量验收未通过，本次不创建验收commit。

运行版本 `full-interview-v1.29.0`，6骨架＋56模块题＝62题/193要素；模型固定DS Pro/high。manifest为 `2d2a28c55724d426a9f32927da7e94f8f6a63b3d7d2c3eb3b183298a1ddb2686`，镜像为 `sha256:44602262fe8cbfa64ddfb30dd8ce4c743529e7c033611ca97e68aac54a6b806a`。

发布目录 `/opt/shinian-releases/interview-manual-c33-20261018T055623Z`，备份目录 `/opt/shinian-backups/interview-manual-c33-20261018T055623Z`。切换时业务表/媒体指纹完全一致，保留4人物、14回忆、44会话、254消息、41媒体文件。认证、TLS、原有效模型密钥、其他功能模型配置、端口和媒体卷保留。Nginx读取超时改为450秒。

验证包括26项后端离线检查；同镜像独立候选的真实DS骨架/幂等与FM03抱怨场景；正式HTTPS匿名401、原家庭认证读取、13张回忆照片正常读取、6模块题数及新骨架目录；正式162个源码文件、运行镜像和pin一致。所有公开证据见evidence/manual-c33-*.json。未宣称本次已更新用户iPhone安装包或完成App端人工验收。

三连轮验收仍为未通过。v1.29定向10检查点执行9项、通过6项，另1网络失败；所有旧失败、争议和日志保留。此前已通过的单轮不能拼成三连轮。此次上线只因用户新授权，不是放宽验收规则。

维护时沿用本次目录中的受保护 `production-override.json`，不要用旧auth发布目录的旧镜像配置重建API。既有新schema写入后，停用新会话时仍保留当前兼容读取代码和runtime；不自动恢复数据库快照。


## 2026-10-18: thinking disabled by user requirement

Production is now `full-interview-v1.29.1`. Every extraction, review and repair request explicitly uses `thinking.type=disabled`; `reasoning_effort` is omitted. The adapter rejects thinking-enabled artifacts; new DS evaluation calls reject thinking-enabled profiles. Original freezes and failure records remain unchanged.

Real DS transport smoke: extraction 4.44 s, review 3.33 s, total 8.18 s; both report 0 reasoning tokens. This verifies configuration and transport, not semantic acceptance. Local checks passed: 11 adapter, 12 workflow, 4 runtime-selection tests. Production HTTPS health, existing family access and question catalog passed; ports, volumes and other environment variables were preserved.

Current protected deployment configuration: `/opt/shinian-releases/interview-no-thinking-20261018/production-override.json`. Do not print its credentials. App reinstall is unnecessary. Formal quality acceptance remains incomplete; no acceptance commit was created.
