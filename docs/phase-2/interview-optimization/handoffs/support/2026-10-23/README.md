# 本轮部署与验证辅助源码归档

这些文件记录 2026-10-23 最终实际使用的发布、验证和导出实现，属于交接资料，不会被产品构建自动加载。产品修正仍是 `770f841`。脚本中保留了当时的绝对路径、release 身份与本机资料依赖。

- `release_on_host.py`：保留 v2 配置、候选隔离、备份、带 stdin 的指纹核对、Compose 前置切换标志及兼容回退；测试用完整目录层级运行。
- `candidate_http_probe.py`：真实 MySQL HTTP 与模型的 12 项业务检查，包含完整题序和真实下一题文本。
- `cloud_api_dialogue.py`、`persona_queue.py`、`sample-cutoffs.json`：独立家庭真实 HTTPS 采样与材料约束受访者队列；三个模块在完整九轮 API 回答后截取。
- `export_cloud_dialogues.py`、`verify_cloud_dialogues.py`：原样导出与独立审计，保留采样终止和后台真实阶段。
- `source-manifest.json`：本轮 30 个 app 补丁文件及基线文件的指纹，不是秘密环境配置。

文件 SHA-256 在 `SHA256SUMS.json`。审阅时与本轮问题表逐项对应。下一轮由 Codex 生成新的候选 SHA、唯一 release 路径和候选身份，检查现场后验证；已有 release 的 prepare 不能盲目重跑。

本目录不含人物材料、完整请求响应、账号、API key、服务器 env 或数据库备份。复跑采样还需要另交的四份人物配置及受保护认证状态；认证由接收环境生成，不从交接包复制凭据。完整 full45 评测另有资料依赖，按本轮回执列出的范围获取。

`verify_cloud_dialogues.py` 的完整审计还依赖受保护 HTTP journals 和服务器提取的骨架记录。附件中的原样问答、审计结果和脚本可供审阅，但仅凭这些附件不能重新执行全部 1083 项检查；需要复跑时，由 Codex 补齐脱敏输入并为接收环境调整路径，保留原结果作为历史证据。
