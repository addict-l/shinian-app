# 2026 年 10 月 23 日云端发布与问题回传

方向：Codex → Claude。生产已发布，题序工程缺陷已修复，采访质量仍有待办。下一轮先继承 `770f841`，再优化下文 C01–C03。协作步骤和双向模板见 [SOP](../collaboration-sop.md)。

用户先授权直接发布候选并导出真实云端问答；MySQL 候选发现题序缺陷后，又明确选择“先修顺序并验证后发布”。本轮只新增题序修正，没有改题库、提示词或其他采访收口策略。正式连续三轮质量门槛没有宣称通过。

## 一 固定版本与生产状态

| 项目 | 本轮实际值 |
| --- | --- |
| 候选基线 | `ac9fd109430f746dcb9efa7800a0ba182941e57d` |
| Claude 候选 | `857787b4bb528f30b4b96252b5299260f4d0064a` |
| Codex 整合及生产代码 | `770f8419c76e1edc7205c76e88c97100dbdf17b1` |
| 共享分支 | `interview/question-optimization`，产品修正已推送；本轮没有合入 `main` |
| pipeline | `v3j_v4d`，判定与说话层同时启用；代码默认值仍为 v2 |
| 模型 | `deepseek-v4-pro`，thinking disabled，省略 `reasoning_effort` |
| v3j runtime pin | `8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f` |
| 生产镜像 digest | `sha256:6f872aceff2112b0100669430bd4164f936c4461c6a5faa3e17ef3688b464532` |
| 发布目录 | `/opt/shinian-releases/interview-v3j-v4d-770f841-20261023` |
| 正式接口 | `https://aimemory.47-82-83-74.nip.io` |

本回执及 SOP 的后续文档提交不代表又发布了产品；生产代码仍以上表固定 SHA 为准。下一轮从共享分支最新头继续，同时确认 `770f841` 的修正已经继承。

## 二 Codex 的产品修正

提交：`770f841`，标题 `fix(interview): preserve frozen skeleton order after JSON persistence`，共 3 个文件、68 行新增、6 行删除。

**复现**：候选 MySQL 数据库中，回答“我是1956年出生的。”后，实际回复为“1956年，那您知道自己的名字有什么来历吗？”，接口也转到 `SK02`；预期应为出生地点 `SK01b`。

MySQL 返回的对象键序是 `SK01, SK02, SK03, SK04, SK05, SK06, SK01b, SK01c, SK03b, SK03c, SK03d`。原实现依赖这个对象的遍历顺序；SQLite 未自动重排，因此此前本地通过不能覆盖此问题。冻结题库要求 `SK01 → SK01b → SK01c → SK02 → SK03 → SK03b → SK03c → SK03d → SK04 → SK05 → SK06`。

| 改动文件 | 修正及继承要求 |
| --- | --- |
| [contract_life_overview.py](../../../../cloud-deployment/backend/app/services/contract_life_overview.py) | `question_ids(data)` 从会话保存的 runtime 取得冻结顺序；`active_id` 保留更正目标和 pending 请求优先；`view` 的字段与题号统一用该顺序 |
| [contract_v3j_life_overview.py](../../../../cloud-deployment/backend/app/services/contract_v3j_life_overview.py) | `next_question` 复用相同题序，保证说话层实际说出的下一题与接口一致 |
| [test_contract_interview_workflow.py](../../../../cloud-deployment/backend/tests/test_contract_interview_workflow.py) | 新增两个回归方法：MySQL 式重排下的完整题序，以及已有进度、pending、更正和 v3 下一题文本；SQLite 夹具用 `flag_modified` 强制保存重排，否则字典相等比较会使测试未真正落库 |

保存的原话、字段、已完成状态和单题 pipeline 标记没有重写。旧 v1 六题、v2/v3 十一题继续按各自保存版本运行，无数据库迁移，runtime pin 不变。旧主线也有同一对象顺序依赖，不能归因成 Claude 本轮新增的业务回归。

复现新回归：在 `cloud-deployment/backend` 运行两个测试方法 `WorkflowTests.test_skeleton_catalog_order_survives_mysql_json_reordering`、`WorkflowTests.test_existing_skeleton_progress_and_correction_keep_catalog_order`，其模块为 `tests.test_contract_interview_workflow`。完整 MySQL + 真实说话层的验证另见下表候选业务探针。

## 三 部署和验证工具的问题及修正

这些修正属于 Codex 的发布辅助工具，不属于产品提交 `770f841`。最终相关源码归档在 [support/2026-10-23](support/2026-10-23/README.md)，随本轮文档提交版本化；文件指纹见该目录清单。它们保留本次机器路径与发布身份，只供审阅和复现设计，下一次发布由 Codex 按新提交生成参数并重新审计，不直接重跑旧 release。

| 问题和触发 | 实际处理 | 后续要求 |
| --- | --- | --- |
| SSH 能建立连接但曾在密钥交换或认证后挂起/断开，HTTPS 正常 | 临时通过用户登录的 Workbench 检查；用户提示代理可能开了全局模式后，SSH 直连恢复 | 先做短超时只读探测；保留原始错误。代理为可能因素，未证明根因；认证、握手、会话执行分别定位，不靠重复改密钥解决 |
| Workbench 下载固定提交的备用 bootstrap 打开既有 `/tmp` 包时发生 `PermissionError` | 没有创建 release 或切生产；改用 SSH 上传至受控目录，再由受权进程准备归档 | 每轮用明确归属和唯一文件路径，校验 SHA；保留旧材料后续跑，不把上传失败当发布成功 |
| 探针 `run()` 中 `checks +=` 使 `checks` 变成局部变量，首次 append 就失败 | 明确 `global token, checks`，重新核对实际上传脚本 | 部署前也要检查验证工具；工具错误与产品错误分别记录 |
| `activated=True` 放在 Compose 成功返回之后，部分替换后报错可能选错恢复分支 | 在执行 Compose 替换前设置标志；之后异常应用预建兼容 fallback | 备份阶段失败恢复旧容器；容器替换开始后的失败使用兼容配置，不只凭命令返回码猜是否改过服务 |
| 镜像内 `/app/tests` 的目录层级使 `BACKEND.parents[1]` 越界 | 在临时容器还原 `/validation/cloud-deployment/backend` 层级，连接实际 app 运行测试 | 不因容器布局而删测试或跳过失败；有外部资料依赖的项目单独列 skip |
| 停服数据指纹脚本通过 stdin 传给容器，但 `docker run` 缺 `-i`，返回空输出，JSON 解析失败 | 首次切换前已恢复旧服务，首轮备份保留；补 `-i` 后重新核验并发布成功 | `docker run -i … python -`；不能把空输出当“零条数据”或绕开指纹核对 |
| 配置和现场依赖可能发生隐式变化 | 准备阶段校验网络、媒体卷、环境换行；Compose JSON 环境值中的 `$` 写成 `$$` 后，再检查实际容器环境等于原值加本轮必要变量 | 保持旧 v2 runtime、认证、端口、卷及其他环境；只回传非秘密元数据 |

发布期间数据库、媒体、源码与 Nginx 备份校验通过；切换前后业务数据指纹一致，端口、卷和其他运行变量保持。此指纹结论对应切换期间；之后独立测试家庭新增问答属于预期写入。首次失败与恢复也保留在 `cloud-deployment-verification.json` 的 `activation-attempt-1.json` 记录中。

## 四 本轮测试证据与解释范围

| 验证 | 结果 | 解释范围 |
| --- | --- | --- |
| 早先候选 `857787b` 的真实判定层直调 | 45 位开发人物、198 case、204 检查点、79 道题；197/204 = 96.57%；judge 204 + verify 56 | 单次开发集判定评测，未包含 speaker、完整云端流程或留出集；不算正式三连轮验收 |
| 最终本地单元/接口套件 | Ran 62，skip 3，其余通过 | 外部评测资料缺失的类明确跳过；不是 62 个实际测试全部通过 |
| 云端容器套件 | Ran 62，skip 4，其余通过 | 容器缺少仓库外资料及完整冻结目录；跳过项目继续保留 |
| 独立候选 MySQL + HTTP + DeepSeek | 12 项业务检查通过 | 完整 11 题顺序及真实下一题话术、重试幂等、暂停继续、跳过、review/confirm、模块草稿入口等 |
| 正式 HTTPS 双层问答 | 4 段、34 轮、68 个唯一模型响应 ID；judge/speaker 各 34 | 使用独立测试家庭；受访者依据公开材料由 AI 模拟；未生成或保存回忆 |
| 原文和审计一致性 | 1083/1083 项通过 | API 请求/回复、参数、pin、请求摘要、provider ID、HTML/TXT/ZIP 一致并通过凭据检查；不表示采访质量 100% |
| 指定 iPhone 17 Pro | 真实 GET health、身份及 4 段 state/conversation 通过，原产品嵌套 Codable 解码一致 | 独立只读工具；未完成产品 GUI 发言、草稿与保存的端到端测试 |

本轮模拟受访者由 Codex 独立代理担任，执行记录未单列代理的具体模型版本；没有另做 Claude Haiku 自然度量表评分。台账中的 Haiku 模拟和评分数字属于原离线评测。

骨架片段为 7 轮，展示前五题并保留下一题；完整 11 题来自另一候选探针。童年、工作、家庭各 9 轮后因重复提示结束采样，后台仍为 `supplement`，`natural_completion=false`。每段另有第十条 AI 队列回答未 POST，未计入 34 轮，也没有漏掉已经发生的 API 操作。

本轮证据附件提供原样问答、脱敏审计、测试和发布摘要及辅助脚本。原始 full45 数据/gold/缓存未进入 Git；本次早先判定成绩的完整复跑资料仍位于 Codex 本机验证区，远端 Claude 若需要复跑，由 Codex 按 SOP 补交受控数据包，不能凭本摘要声称已经独立复现。

本轮附件也未包含四份采样人物配置、受保护 HTTP journals 和服务器提取的骨架记录。归档脚本保留这些依赖和历史路径；完整采样或 1083 项审计的重跑须先补齐脱敏输入、重新生成接收环境认证并调整路径。现有附件是原问答与检查结果的可读证据，不是完整一键复跑包。

## 五 Claude 下一轮待办

| 编号 | 原始输入或触发 | 实际行为与预期 | 已复现范围 |
| --- | --- | --- | --- |
| C01 | “那时候下工累了就歇一会儿。”“不是累了，我还想接着聊。”“她不想说，后来我就没有再问。” | 历史、否定或第三方用词被当作本人当前暂停/拒答；应按主体、时间及否定语境识别当前控制意图 | 隔离 API + 固定模型夹具；不是云端真实模型复现 |
| C02 | “我们是在工厂认识的。后来天天一起上下班，慢慢就熟了。这段我不想多讲。” | `ready` 先于 decline 信号，仍给草稿入口；按已确认拒答边界处理，本轮不静默改变该优先级 | 同上；代码检查点在 `app/ai/interview_speaker.py` 的收口决策 |
| C03 | 三个模块中多次回答“没有了，就这些。”等 | 仍重复“这段可以先整理成草稿了。您还有什么想补充的吗？”；需要明确无补充后的自然收口与草稿操作衔接，按业务基准给出方案和回归 | 正式 HTTPS + 真实双层模型；原样保留九轮并如实截断 |

建议下一轮先处理 C03 与 C01/C02 的控制意图回归，再评估新的说话措辞。修复时区分“资料足够”“没有补充”“明确拒答”“同意生成/保存”，不得从一个状态推断另一个授权。若方案改变已确认业务边界，先由用户确定取舍。

Codex 后续负责：验证 Claude 方案接入真实状态机后的行为，重跑对应 MySQL/HTTPS 场景，按授权部署并回传。每个修复要引用原问题编号，保留失败输入及前后实际输出。

## 六 回退与资料入口

回退使用本次具备 v3 能力的镜像，保留 `INTERVIEW_V3J_RUNTIME_DIR` 和 `INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256`，只把 `INTERVIEW_PIPELINE` 切回 `v2`。已开始的 v3 题仍按其标记完成。现成兼容配置为发布目录内的 `fallback-v2-override.json`；凭据配置及备份留在服务器，不进本附件。不能用不识别 v3 状态的旧镜像接管进行中的题，也不能恢复旧数据库来覆盖发布后的真实数据。

本机完整证据根：`/Users/student03/Desktop/shinian-validation/artifacts/interview-cloud-20261023/`。重点文件：`delivery-summary.json`、`cloud-deployment-verification.json`、`independent-dialogue-verification.json`、`ios/simulator-postdeployment-report.json`；题序首次失败另在受保护验证区，原始真实家庭数据不在这些问答附件中。

问答阅读目录：`/Users/student03/Documents/ChatGPT/ai memory/exports/云端双层采访问答_2026-10-23/`。跨机器阅读使用本轮交给用户的附件包，包内路径、文件 SHA-256 和可用范围见 `附件清单.json`。接收方尚未读取或缺少附件时，记录为“待接收/证据待获取”，不声称已经通知或完成了对方的复验。
