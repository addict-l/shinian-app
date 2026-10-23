# C01–C03 整合、发布和验证工具

本目录保存本轮 Codex 辅助工具源码，不进入产品运行路径。产品整合 SHA 为 `ed38ab2c4738874d01b4470a10a8826c1c3da90d`。工具的配置路径、固定版本、镜像、容器、端口及 host 属于本次现场，下一轮须重新生成并审查，不能重跑旧 release。

- `prepare_candidate.py`：固定归档、源码/pin 核对、容器测试、隔离 MySQL/媒体、独立 TLS Nginx、全量生产环境保留与 v2 fallback。首次执行遇到验证 tools 不全及端口占用，保留失败证据。
- `resume_candidate.py`：从既有 release 续跑，补齐同一 SHA 的 46 份 tracked tools，使用随机 loopback 端口；不删除既有库、媒体或别人的候选。
- `legacy_setup.py`：同一候选镜像、同一隔离库、pipeline v2 的准备服务，用显式 API 跳过骨架后再经 v3 接口验证模块；未用于生产发布后验证。
- `activate_release.py`：要求显式 gate 文件；检查正在运行镜像与完整环境、pending；备份真实执行的 `/app`、数据库、媒体、Nginx/TLS；在关闭公网写入窗口内比较全表和媒体指纹，再切换；异常使用仅 pipeline=v2 的兼容配置。备份与环境留在服务器。
- `ios-display-probe/`：本轮实际使用的模拟器独立显示投影源码和来源哈希；未运行完整产品 GUI。
- `cloud_preflight.py`：只读现场配置与 JSON pending 计数，输出非秘密元数据。
- `verify_candidate_https.py`：生成独立测试家庭。默认候选 15 场景；`--postrelease` 生产 9 场景。不传 forward 端口时访问正式公网 HTTPS。老人输入是固定验收句或上轮公开材料 AI 回答的逐字重放；判定/说话层为新真实调用。认证只存 `--private-dir`，不会复制到问答附件。
- `extract_test_family_records.py`：依据该次 private auth 的合成用途标记和人物 ID 白名单，只提取独立测试家庭骨架审计；不导出真实家庭、全表或凭据。
- `audit_live_records.py`：从原始响应、payload、参数及 pinned system prompt 重算请求摘要，检查模型、response ID 一致性；usage 中 reasoning tokens 缺失时写 null，不冒充 0。
- `export_verbatim.py`：从最终 API messages/life_overview.turns 取原文；保存原始 journals、setup 与按钮操作；HTML 解析回读逐字核对，白名单打包并扫描实际凭据值。源码中的 key 文件引用是只读扫描入口，文件本身及其内容不交付。

附件的 `原始记录/{candidate,production}-https` 含各场景响应、家族限定的 server-skeleton-records、审计与 HTTP journals（无注册/登录凭据）。离线重新核验可在完整仓库中运行：

```sh
python3 <本目录>/audit_live_records.py <附件>/原始记录/candidate-https \
  --runtime-dir cloud-deployment/backend/app/ai/interview_runtime_v3j_v4d
python3 <本目录>/audit_live_records.py <附件>/原始记录/production-https \
  --runtime-dir cloud-deployment/backend/app/ai/interview_runtime_v3j_v4d
```

重新采样会新建测试账号与人物并产生真实模型费用，先确认环境及本轮授权；不要复用交接材料中的旧认证。完整缓存回放另需 Claude 交付的 `claude-interview-replay-data-20261023.zip`（SHA-256 `f8b39141903954ad7d52415b9e84f724e57bb93a841a1493e6d3828749b3f8b7`）；holdout 不用于调参。

本目录只含工具和文件指纹，不含 QA 原文、缓存、gold、账号、生产 env、凭据或业务备份。SHA 清单随最终文档提交生成；原失败日志与最终结果在交给用户的问答附件中保留，不能把原失败算作已通过的验证。
