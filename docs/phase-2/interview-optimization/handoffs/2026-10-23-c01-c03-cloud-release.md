# 2026 年 10 月 23 日 C01–C03 整合、发布与回传

方向：Codex → Claude。**候选验证通过，生产已切换；正式连续三轮质量门槛仍未宣称通过。** 本轮遵循 [SOP](../collaboration-sop.md)。原失败及工具恢复过程保留在附件，不把后续通过改写为首次即成功。

## 固定版本与授权

| 项目 | 实际值 |
| --- | --- |
| 接收分支 / base | `interview/claude-c01-c03` / `d6b11f349b9a68ab87b4baf886ea8497c371f137` |
| Claude 代码 / 交接单 | `ece64ead178ec03be1d78a0e4cfba9e8b5735e9d` / `50572ccb8c1dbcc69f65711a05a6a5bea270fa1d` |
| 整合及生产代码 | `ed38ab2c4738874d01b4470a10a8826c1c3da90d` |
| 整合来源 | 保留 Claude 历史，并正常合并 `main` 的 `246a2c4633dcbc49a7dc1ce0dcb55fd9501ab984`；继承 `770f8419c76e1edc7205c76e88c97100dbdf17b1` |
| 共享分支 | `interview/question-optimization`；代码与本回执已推送，**没有合并 main**；后续文档提交不代表再次部署 |
| 发布前生产 | `649b5b900244fd3742f3226f8e2b6d9d07387992`，含 OSS；不能把上轮采访回执的 `770f841` 当作本轮切换前整台后端版本 |
| 生产镜像 | `sha256:b33819f706e40bf46b23fcce5f3a88252d4cb0c9904698417232e99c60332fac` |
| 后端 Git tree | `b30057cefee207d3e9fdd6aad71141e291b3d25e`，镜像内 265 份 tracked 后端文件逐份核对 SHA |
| pipeline / 模型 | `v3j_v4d` / `deepseek-v4-pro`，thinking disabled，不传 `reasoning_effort` |
| runtime pin | `8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f`，题库、说话层提示及模型配置未改 |
| 生产 release | `/opt/shinian-releases/interview-c01-c03-ed38ab2-20261023` |
| 权威源 / 配置 | release 内 `source/cloud-deployment/backend/` / `production-override.json`；完整环境和私有 OSS 挂载保留 |
| 正式入口 | `https://aimemory.47-82-83-74.nip.io` |

本轮授权来自用户明确要求：“上面 1、2 全部通过、且没有发现新的业务取舍问题时，授权按 DEPLOY_ALIYUN.md 把整合后的代码发布到生产”，保持 pipeline/pin，准备只切 v2 的 fallback，不合并 main。Claude 交接单“未获发布授权”是交接时的历史状态，本轮沿用随后的人类授权。

## Codex 的整合与修改

- 在独立工作树接收固定 SHA，主工程未提交的后端实验没有带入；`ed38ab2` 正常合并当前 main，保留线上 OSS 与其他已发布代码，没有重写 Claude 的 C01–C03 产品规则。
- 发布前比较实际生产 257 份后端文件与已知基线；候选镜像核对本轮 265 份 tracked 文件，runtime `--check` 通过。原镜像没有的测试随新镜像复制，不涉及运行协议或数据库迁移。
- 本回执所在文档提交：更新 [采访业务基准](../../../interview-development-baseline.md) 的 v3 C01–C03 已确认例外、台账及项目环境当前生产引用；归档本轮辅助工具。默认 v2 的规则没有重写。
- 下一轮必须继承 `ed38ab2`，包括此前的 `770f841` 题序修正和 main 的 OSS 整合；从本回执后的共享分支最新头继续，不能从旧 `d6b11f3` 再起一轮并覆盖整合。

## 验证结果与口径

| 验证 | 本轮实际结果 | 范围及限制 |
| --- | --- | --- |
| 本地后端全部测试 | Ran 79，skip 1，失败/错误 0 | venv；固定夹具、真实 Node 引擎、SQLite 和缓存回放。跳过旧 `FrozenParityTests` 的外部整题冻结资料；不是 79 项全执行 |
| 云端镜像全部测试 | Ran 79，skip 1，失败/错误 0 | 同一代码与资料，容器 network=none，恢复仓库层级；无真实 provider 调用 |
| full45 回放 | 204 检查点，259 请求（judge 204、verify 55），0 cache miss、0 与旧结果差异，197/204 | 缓存一致性，不是新的一轮真实质量成绩；SK 经骨架入口 64 检查点、72 请求，0 差异、0 投影差异 |
| sim-hv4d 回放 | 模块 21 判定 + 骨架 14 判定一致；说话层输入 21+10 一致；69 缓存请求，0 miss | 补充阶段没有旧缓存，另用下方真实验证 |
| 云端隔离候选 MySQL + HTTPS | **15 场景、89 检查通过** | 完整 11 题题序与实际下一题、暂停继续、重复幂等、显式跳过、更正及 review/confirm；C01 模块及骨架正反例、C02 两类拒答、C03 三模块与内容加结束 |
| 候选原始调用独立审计 | **529 检查，52 唯一真实响应**：judge 25、speaker 27、verify 0；provider 失败 0 | API 和限定测试家庭 MySQL 骨架审计合并去重；仅 API 可见记录的 30 次不是总次数 |
| App 显示投影 | 指定 iPhone 17 Pro 模拟器独立可执行程序：13 份实际概览解码、10 份 known/partial 原话投影通过 | 使用真实 `LifeOverview.swift` 和 `CareLifeSummaryGroups` 源码、记录文件哈希；常规与关怀显示均保留原话。不是完整产品 GUI 发言/保存测试 |
| 生产发布后正式 HTTPS | **9 场景、59 检查通过** | 独立新测试家庭；C01 四例、C02 两类、C03 三模块；骨架准备全部经生产 v3 API 显式跳过 |
| 生产原始调用独立审计 | **830 检查，117 唯一真实响应**：judge 14、speaker 103、verify 0；provider 失败 0 | 包含 90 次骨架准备 speaker；C01–C03 模块本身 27 次真实响应，不能把准备调用算成质量样本 |
| 导出原文 | 24 段、136 条问答，HTML 解析回读与 canonical JSON 逐字一致，TXT 逐条包含；ZIP 哈希校验及实际凭据值检查通过 | “审计通过”不等于采访质量满分；原始 journals 包含准备、按钮、更正、重复与超时 |

重放资料 SHA-256：`f8b39141903954ad7d52415b9e84f724e57bb93a841a1493e6d3828749b3f8b7`；full45 数据 SHA-256：`3a8c7e50b2d7aa2540f071a9183101d0866dcba8d7dc103813910d071b605325`。已校验 ZIP 路径、无链接和 CRC，配置 `SHINIAN_EVAL_HOME` 后完整复现上述缓存结果。holdout 未用于调参，本轮也没有声称完成留出集验证。Claude 的 915 段影响检查未作为本轮新增独立结果复报。

候选 TLS 采用有效正式证书的独立 loopback Nginx，经 SSH 转发校验证书与主机名；没有改生产 Nginx。模块准备使用同一候选镜像和隔离库的 v2 sidecar 显式跳过骨架，再经实际 v3 接口选模块；完整骨架另有新 v3 场景。发布后没有 sidecar，全部是公网 HTTPS。

真实网络失败重试为：客户端在提交后强制读取超时，保留首次失败 journal，以同一 client_request_id 重试成功、只产生一次回答。它不冒充真实 provider 故障；provider 故障后的复用与说话层失败回退由夹具测试覆盖。保留了最初转发尚未监听时的连接拒绝记录。

## C01–C03 实际结果与原话

受访者输入为固定验收句或上轮公开材料 AI 回答的逐字重放；没有新 AI actor 读取内部 gold/字段，也不是用户真人实时采访。判定与说话层是本轮新真实 DeepSeek 响应，没有使用模型回复缓存；没有 Haiku 评分。

- C01：三句“那时候下工累了就歇一会儿。”“不是累了，我还想接着聊。”“她不想说，后来我就没有再问。”，候选模块/骨架、生产模块均继续本题。生产对第三句实际说“她不想说，您就没再问。那您有过伴侣关系的经历吗？”。本人当前休息句仍暂停，继续后回到入口。
- C02：有内容后“不想多讲”，生产原话是“好。这段可以先整理成草稿了。您还有什么想补充的吗？”，phase=supplement，有草稿入口、无目标追问；随后“没有了，就这些。”进入 review。**草稿原句的可选补充问句仍在**，按交接单已披露取舍保留，不能报告成完全没有问句。无内容时跳到下一题，没有草稿入口。
- C03 童年：补充后“后来妈妈写给您看，您就明白了。您还有别的想补充的吗？”，无补充后“好，先核对这段草稿，您确认后再保存。”；工作与家庭同样直接 review，均不重复整句草稿提示，无补充这次不新增 provider 调用。
- 生产工作补充阶段有一轮只说“您还有别的想补充的吗？”。模型重复了上一次“您把两百块寄回家，九十块留作零用，安排得挺清楚。”的承接，既有 `repeat_ack` 去重后 ack 为空，按交接单回退为短问句。另一次初次草稿收尾也因承接清洗只发固定句。这些是实际效果，原文和 fallback 审计保留；provider 调用本身成功，不能把两者混为“模型未调用”。

C03 三模块、C02 有内容场景均自然到题内 review，未生成或保存回忆。C01 继续追问/暂停恢复、无内容拒答后的下一题，以及部分骨架负例为有限验收片段：`sample_cutoff=true`、后台实际 phase/题号保留；完整骨架到 confirmed。附件逐段注明 natural_completion，不把到 review 宣称成已保存。

## 发布、数据与回退

发布前生产 pending 扫描及关闭公网入口后再次扫描均为 0，包含 `pending.calls.speaker=0`；不存在需要旧说话任务摘要续跑的挂起调用。切换后复查仍为 0。C02 骨架已答但有限的状态为 known，App 两类文本投影保留证据，没有显示成拒答占位。

实际执行源码 `/app`、MySQL、媒体、Nginx/TLS 和环境备份位于上述受保护 release，归档可读、SHA/尺寸已记录。维护窗口关闭公网 Nginx 写入，停旧 API，比较切换前后全部表及媒体 SHA：一致。30 条 memories、30 条 memory_drafts、54 份 media_assets/本地媒体，以及其他业务表均保持；指纹结论仅对应切换窗口，之后独立测试家庭新增问答是预期写入。OSS 访问配置、凭据挂载、媒体卷、端口和完整实际容器环境与切换前一致。没有恢复旧数据或删除数据卷。

健康 HTTP/正式 HTTPS 200、数据库 ok；匿名 `/api/v1/auth/me` 401，独立家庭注册和受保护业务接口通过。`CLOUD_VERSION.md` 指向实际 release。旧 `/opt/ai-memories/backend/app` 是历史源码，不作为当前执行版本或正确备份来源。

兼容回退预备为 release 内 `fallback-v2-override.json`，已检查与生产 override **唯一差异为 `INTERVIEW_PIPELINE=v2`**。回退仍用本轮能识别 v3 状态的新镜像，保留 v3 runtime 两变量、原 OSS、认证和数据。已开始 v3 的题按标记结束；不直接换不识别状态的旧镜像，不自动还原数据库。此次无需执行 fallback；“已准备校验”不冒充本轮做过故障回退演练。

## 工具问题、修正及可读源码

最终工具归档于 [support/2026-10-23-c01-c03](support/2026-10-23-c01-c03/README.md)，含源码、source manifest、gate 和 SHA256SUMS。它们不属于产品逻辑改动。

| 触发 / 原错误 | 处理与影响 |
| --- | --- |
| GitHub 直连不稳定 | 只对 Git/gh 子进程使用本机 HTTP 代理；SSH 直连。没有改全局网络配置 |
| 初次本地缺 replay 资料，Ran 76、skip 3 | 接收用户 ZIP 并核对哈希，重新运行最终 Ran 79、skip 1；旧结果保留，未用 skip 代替回放 |
| 云端单测缺 `/validation/tools/run_full_interview_eval.py` | 初始工具筛选范围不足；补齐固定 ed38ab2 的全部 46 份 tracked tools，再在完整仓库层级跑全部测试，未删测试或改产品镜像 |
| 候选固定端口 18012 被另一个隔离服务占用 | 本轮容器未启动，仅移除属于本轮的 created 容器后续跑，保留本轮库/媒体，改随机 loopback 端口；没有停别人的候选或生产 |
| HTTPS 首次 ConnectionRefused | SSH 转发尚未绑定；核验 TLS 监听后以同一操作日志恢复，此次错误之前无 API 写入；不能当成模型失败 |
| 独立审计遇到 `completion_tokens_details=null` | 用 `or {}` 兼容；原失败保留。reasoning_tokens 未提供时报告 null，参数与请求摘要仍核对 thinking disabled |
| gate 本机适配时误用审计字段 `all_passed` | 按实际审计 `passed` 修正，发生在上传执行和停服前；全部结果重新断言后才生成 release gate |
| 停服/Compose 部分执行后异常可能选错恢复分支 | 停止尝试前设置阶段标志、恢复 finally 保证尝试重启 Nginx；Compose 前设置 switched；保持 v2-only fallback。此次发布成功，未触发异常路径 |
| 审计及导出可复核性 | 增加显式 runtime-dir 参数、限定测试家庭提取器、HTML 回读、实际凭据扫描；保留原发布前审计字节及其 gate SHA，工具复核的新运行另存 rerun |

## 未解决及下一轮责任

- Claude：从最新共享头继续；引用 C01/C02/C03 本轮已通过证据。继续保留 C02 原草稿固定问句的业务说明、显式跳过边界。若要改话术或这两条规则，再按业务基准确认，不在下轮顺手改。
- Claude：说话层仍可能复述得平、重复上一承接而被清洗，生产工作场景已有真实样本；可提出下一轮候选，但本轮没有改提示词或重新设计收口。
- 仍存在：only 无补充话语虽不再加入判定 sources，v2 共享 `current_sources/narrative_sources` 仍可能包含该消息；繁体信号和未列称谓等覆盖限制同 Claude 原交接单。本轮不擅自扩范围。
- Codex：后续整合继续检查 pending digest 跨版本风险、固定 SHA/镜像/OSS 引用和证据白名单。完整产品 GUI 发言/生成/保存端到端、真正 holdout、Haiku 新评分及正式三连轮门槛未完成，不包装为本轮通过。
- 上轮 v2 全链逐字节对照脚本未重跑；v2 路径未改，本轮有默认 v2 夹具和候选 v2→v3 按题切换覆盖，不能称为重新做过完整逐字节对照。
- 本轮没有新增待用户决定的发布前业务取舍。上述既有质量待办与本轮特定验收通过分开记录。

## 附件及接续

交给用户的附件：`C01-C03问答与原始核验.zip`，SHA-256 **`8d89eb12e29711c22f480fe483fa220b9bf790d340180dea39bf3ea62266bfdd`**，1644578 字节。内含 24 段原样 HTML/TXT/canonical JSON、136 条问答、脱敏原始 HTTP journals（含失败/重试/准备）、限定合成家庭骨架记录、两次独立审计、单测日志及辅助工具；不含认证、key、真实家庭原始数据、数据库/媒体备份或 full45 gold/缓存。

本机阅读入口：`/Users/student03/Documents/ChatGPT/ai memory/exports/C01-C03云端双层采访问答_2026-10-23/云端双层采访问答.html`。该路径只供本机打开；Claude 云端接收需要用户上传上述 ZIP。源码和摘要已在共享分支可读取；附件已生成交给用户，**未声称 Claude 云端已接收或完成复验，也未向其他聊天自动发消息**。拿不到附件时注明访问缺口，不能只凭本机路径宣称证据已取得。

下一轮基线：共享分支最新头（包含产品 ed38ab2 与本回执文档提交），双方分别记录新候选固定 SHA。复现离线审计的命令与依赖见 support README；重新采样使用新认证及新的隔离身份，不复制旧 token。
