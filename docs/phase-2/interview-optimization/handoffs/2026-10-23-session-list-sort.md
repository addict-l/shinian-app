# 2026-10-23 采访入口数据库排序修复回传

方向：Codex → Claude。**候选验证通过，生产已发布，模拟器采访入口恢复。** 本轮是数据库查询的工程修复；采访质量沿用上轮结论，没有新增真实模型问答或正式三轮质量成绩。

## 固定版本与状态

| 项目 | 结果 |
| --- | --- |
| 接收基线 | `831296007671455ea896df4ed4d939f02f2ab9bc`，已包含 Claude C01–C03、Codex `ed38ab2` 整合、`770f841` 题序及 OSS |
| Codex 修复 / 当前生产代码 | `a1ecee61eae633898f1ba3a7200a630ca66a32c2` |
| 后端 Git tree | `00e39593647f4e062fc08b179851254cf017a259`；265 份镜像后端文件逐一核对 |
| Git | 修复已正常推送 `main` 和 `interview/question-optimization`；本回执是后续文档，不代表再次部署 |
| 发布前执行代码 / 镜像 | `ed38ab2` / `sha256:b33819f706e40bf46b23fcce5f3a88252d4cb0c9904698417232e99c60332fac` |
| 当前镜像 | `sha256:d7b94334ac909feb59775a19b5b27fde48737153ff919bdf83eb2192f809b0d8` |
| release | `/opt/shinian-releases/session-list-sort-a1ecee6-20261023` |
| pipeline / runtime pin | `v3j_v4d` / `8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f` |
| 采访模型 | `deepseek-v4-pro`，thinking disabled，省略 `reasoning_effort`；本轮未改配置 |

用户要求连接真实数据库供 App 测试。准备修复及全部验证后，用户针对“是否将候选 a1ecee6 发布到真实阿里云，修复采访入口的‘数据库暂时不可用’”明确回答“发布修复并恢复采访（推荐）”。依此完成生产发布；没有新增采访业务取舍。

## 问题、修改与下一轮继承

真实 App 新人物的采访入口返回 HTTP 503，显示“数据库暂时不可用”；`/health` 和数据库简单查询仍成功。真实家庭的 `ChatSessionRepository.list()` 返回 MySQL **1038 Out of sort memory**：原查询将包含大段 `information` / 采访审计 JSON 的完整行按 `updated_at` 排序，触发 sort buffer 限制。不是凭健康检查推测数据库已恢复。

修复提交仅有两处：

- `app/repositories/chat_session_repository.py`：同一个 Session 先按原家庭条件、原 `updated_at DESC` 查询轻量 ID，再无排序读取完整记录，并按第一步 ID 顺序返回。保留原接口、家庭隔离、JSON 原文及时间排序，不调大全局 MySQL 内存，不改表或模型。
- `tests/test_contract_interview_workflow.py`：新增大段 JSON 排序回归。旧实现实际触发模拟 1038 失败；新实现检查降序、家庭筛选、空列表及原始大段内容完整性。独立真实 MySQL 另验证真实 1038，单测不冒充真实 MySQL 复现。

Claude 下一轮须从最新共享分支继续，继承 `a1ecee6` 的查询修复及此前 `ed38ab2`、`770f841`、OSS、固定键盘规则；不要把旧完整行排序带回。后续如进一步优化列表数据量，保持家庭隔离、字段完整性及排序契约，单独验证。主工程原有未提交实验未进入本次候选或发布。

## 实际验证

| 层 | 结果与边界 |
| --- | --- |
| 最小回归 red / green | 旧查询在新增回归中因 1038 失败；新查询通过。最初一次错误测试路径的导入失败不计为 red 证据 |
| 本地全部后端测试 | Ran 80，skip 1，失败/错误 0；runtime `--check` 通过 |
| 云端镜像全部测试 | Ran 80，skip 1，失败/错误 0；缓存资料齐备、network=none，无真实 provider 调用 |
| 原缓存回放 | full45 197/204、0 cache miss、与旧结果 0 差异；sim-hv4d 仍一致。属于缓存一致性，不是新的质量轮次；跳过项仍为旧整题 FrozenParity 外部资料 |
| 独立候选 MySQL | 8 份各 1 MiB 合成审计、共 10 个会话；默认 sort buffer 下旧 SQL 真实报 1038，新查询排序、内容、家庭筛选与空家庭全部通过 |
| 独立候选 HTTPS | 会话列表 HTTP 200、10 个会话；新合成人物采访入口进入 SK01 / collecting；无生产数据写入、无模型调用 |
| 发布前真实数据只读 | 候选镜像访问原受影响家庭，旧 SQL 仍报 1038；修复返回 51 个会话且家庭/降序正确。独立连接只读事务，不写真实家庭 |
| 发布后正式 HTTPS | `/health` 200/database ok；匿名 `/auth/me` 401；既有独立测试家庭认证与会话列表 200（9 个会话） |
| 发布后真实数据只读 | 新生产容器读原家庭 51 个会话，家庭条件和降序通过，事务只读 |
| 现有 iPhone 17 Pro GUI | 原会话 GET 200；此前失败人物的 conversation POST 200，随后 GET 200；页面显示人生骨架 1/11 和“您大概是什么时候出生的？”；没有代答、生成或保存回忆 |

模型和采访流程未改，本轮 provider 调用为 0，没有新问答导出；[上轮 C01–C03 原样问答与质量待办](2026-10-23-c01-c03-cloud-release.md)继续有效。没有重新执行上轮 15/89、9/59 的整轮真实模型场景，也没有重新宣称其为本轮成绩。

## 发布与数据保护

停服前及关闭公网入口后两次 pending / speaker 扫描均为 0。备份实际执行 `/app`、MySQL、媒体、Nginx/TLS、环境；归档可读、尺寸和 SHA 已校验。完整表和本地媒体指纹在切换窗口前后完全一致，含 30 条 memories、30 条 memory_drafts、54 份 media_assets/媒体文件。结论仅对应切换窗口，随后用户正常打开采访产生的状态写入不计为切换差异。

完整环境、端口、媒体卷、私有 OSS 挂载和认证配置与旧容器一致。权威源码为上述 release 内 `source/cloud-deployment/backend/`；`/opt/ai-memories/backend/CLOUD_VERSION.md` 已更新。历史部署目录的 Git HEAD 不能代替运行镜像来源。

`production-override.json` 与 `fallback-v2-override.json` 留在受保护 release，唯一差异是 `INTERVIEW_PIPELINE=v2`；回退保持本轮兼容 v3 的镜像、runtime pin 和 OSS，不恢复旧数据库。本次未触发 fallback，不声称做过故障回退演练。候选容器、独立候选 Nginx 及本轮 SSH 转发在验证完成后停止，候选库和证据保留。

固定键盘规则未写入或调整；Windows ToDesk 英文传键、Mac/模拟器简体拼音、实体键盘连接开启、同 Mac 语言开启、独占捕获关闭，继续沿用[用户已确认约定](../../../../.agents/skills/project-development/references/project-environment.md#模拟器实体键盘用户固定约定)。无需重新安装或重置 App、模拟器。

## 部署工具、证据与待办

工具从上轮已验证版本适配本轮固定 SHA、独立数据库/端口、80 项测试 gate 和查询验证；发布仍备份实际容器、保存完整环境及 OSS、比对切换指纹、阶段标志恢复和 v2-only fallback。源码及非秘密摘要见 [support](support/2026-10-23-session-list-sort/README.md)，逐文件哈希见其 `SHA256SUMS`。原激活 `deployment.json` 中发布后业务检查为 pending，是激活时快照；完成结果另存 `production-postrelease-verification.json`，不改写原记录。

排查中尝试读取 `performance_schema` 被现有数据库账号以 1142 拒绝；未提权或改权限，随后通过实际业务查询得到 1038。最初测试路径错误与忽略规则导致的 staging 拒绝都发生在发布前，修正调用方式/显式添加已跟踪测试后完成最终回归；不是产品故障。

交给用户的附件：`采访入口修复证据.zip`，58211 字节，SHA-256 `daeb2aa69a03e0007bbf1f53a8d5a112dae6252ea176efb8ec8dcba885159532`。包含本目录工具/摘要、单测日志、原始 1038 red 和切换日志；不含数据库备份、真实家庭原文/身份、认证或模型凭据。Git 中有可读源码和摘要；附件仍由用户上传给 Claude，未声称 Claude 云端已经接收或复验，未向其他聊天自动发送。

Claude 接续采访优化时引用本回执并保留查询回归；Codex 后续继续核对真实业务接口、运行镜像来源和大 JSON 数据兼容。当前无新增待用户决定事项；上轮采访质量、holdout、真人全流程与三轮门槛待办仍保留。
