# 采访链路优化（分支 `interview/question-optimization`）

2026-10-22 起，采访优化的每个**可提交版本**都推送到 GitHub 分支 `interview/question-optimization`，由用户审阅后合并到 `main`。
离线候选与评测工具不改 `ios/`、`android/` 和线上运行合同。“接入后端”提交块在 `cloud-deployment/backend` 新增了新流程，但开关 `INTERVIEW_PIPELINE` 默认仍是现网 v2：合并、部署而不改配置时，App 与阿里云后端行为不变。启用属于发布，按[开发约定](../../../AGENTS.md)另行完成阿里云与模拟器验证、审核和授权。

## 版本台账

| 版本 | 层 | 结果 | 状态 | 位置 |
| --- | --- | --- | --- | --- |
| 现网 v2 | 抽取 → 复核 → 至多一次修复 | full45 关键点约 70% | 线上（`cloud-deployment/backend/app/ai/interview_runtime`） | `docs/prototypes/full-interview-v2/single-question-v2/` |
| **v3j** | 判定层：每个检查点一次判定调用，代码拼装与引擎校验 | full45 197/204 = **96.6%**；随机 10 人门槛缓存 42/43、关缓存真实调用 43/43 | 离线候选，已测 | `docs/prototypes/full-interview-v3j/` + `tools/interview_eval/pipelines/v3j.py` |
| **v4d** | 说话层：只改怎么说（承接、追问、收尾转题），不改问什么 | 模拟访谈迭代组 8 人 × 4 题：自然 3.97、贴合 4.03、时机 4.69、语气 4.72，硬性违规 2.8%（现网固定话术 2.47 / 2.21 / 2.93 / 3.21，违规 44%） | 离线候选，已测 | `docs/prototypes/full-interview-v4/` + `tools/interview_eval/simulate/` |
| v4e | 说话层：追问恢复“把老人刚讲的事放进问句”，转题不套模板 | 未测完 | 开发中，提示存于 `history/speaker-prompt.v4e-untested.txt` | 同上 |
| **接入后端** | v3j 判定层 + v4d 说话层进入后端访谈入口，`INTERVIEW_PIPELINE=v3j_v4d` 启用 | 离线（0 token）：full45 后端回放 197/204，204 个检查点与 `branch-check-v3j` 逐个相同；sim-hv4d 的 35 次判定、33 次说话层输入与模拟器逐字相同 | 已接入，**默认关闭**；阿里云候选、iPhone 模拟器未验证 | `cloud-deployment/backend/app/ai/interview_runtime_v3j_v4d/`，见下文 |

固定条件：模型 DeepSeek `deepseek-v4-pro`，**thinking disabled**；题库为冻结的 83 题 v2（[冻结清单](../../question-bank-freeze-v2.json)，不得修改）；模拟老人和量表打分由 Claude Haiku 担任，不用 DeepSeek。

## 接入后端（v3j + v4d）

### 切换与回退

| 环境变量 | 取值 |
| --- | --- |
| `INTERVIEW_PIPELINE` | `v2`（默认，现网）或 `v3j_v4d` |
| `INTERVIEW_V3J_RUNTIME_DIR` | 新运行合同目录，镜像内为 `/app/app/ai/interview_runtime_v3j_v4d` |
| `INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256` | 该目录 `manifest.json` 的 SHA-256，当前 `8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f` |

现有 `INTERVIEW_RUNTIME_DIR` / `INTERVIEW_RUNTIME_MANIFEST_SHA256` 照旧保留（题目目录、人生骨架和 v2 流程仍用它）。设为 `v3j_v4d` 时 API 启动即校验新目录：manifest pin、每个文件哈希、目录里没有未列出的文件、三处模型参数只有评测时的五项且 thinking disabled（模型名 `deepseek-v4-pro` 由 manifest 哈希固定）、题号题序与入口问题和现网运行合同完全相同；任一不符则 API 起不来（与现有 pin 相同）。
**回退**：把 `INTERVIEW_PIPELINE` 改回 `v2`（或删掉这一行）并重建 API 容器；没开始的题立即回到 v2。已经在新流程里开始的那一题会按标记用新流程答完，所以回退后先保留两个 `INTERVIEW_V3J_*` 变量，等这些题结束再删。部署步骤见[后端部署说明](../../../cloud-deployment/backend/DEPLOY_ALIYUN.md#采访新流程开关v3j--v4d)。

### 怎样标记新旧会话

按**题**标记：一题第一次进入流程时，把流程名（`pipeline: v3j_v4d`）和运行合同 manifest SHA 写进这一题自己的 `contract_state`；没有这个标记的题都是 v2 写的。已开始的题始终用它开始时的流程，没开始的题用当时的 `INTERVIEW_PIPELINE`。理由：

- 一题的原话、实际问句、待处理调用、已核验字段和审计都在这一题的 `contract_state` 里，题与题互相独立（运行合同 `question_context_mode=independent`），所以在题与题之间换流程不会把旧流程的待处理调用交给新流程，也不会用新流程重读旧答案；每次调用还绑定含 manifest、阶段、参数、提示和输入的 `request_sha256`，不同流程的记录本来也对不上。
- 后端的一个 chat session 只是一段故事（通常就是一题），而人物的整条采访状态会经 `following()` 一直往下传；按整条采访标记会让现有用户永远进不了新流程，回退也到不了已开始的人。按题标记时开关和回退都在下一题生效，与现有 v2 schema 迁移“在题与题之间切换、不重解释旧题”的做法一致。
- 新流程只用于现网 83 题目录（`runtime_version=full-interview-v2.0.0`）；旧 62 题目录的采访继续用旧运行合同。
- 判定结果仍是同一个引擎的结果结构，题内只多了 `followups`、`asked_target` 两项；人物级只多一个 `speaker_last_close`（上次收尾时说话层说的话）。旧镜像读到这些会忽略它们，但会用 v2 重判进行中的新流程题，所以回退请改变量而不是只换旧镜像。

### 调用与持久化

- 判定（judge）、否认复核（verify）、说话层（speaker）三类调用都经 `save_call` 先写进这一题的 `pending.calls` 再进行下一步；重试同一请求时按 `request_sha256` 原样复用，不再调用。说话层调用失败不报错，记为失败并用固定句回退，重试也不再调用。显式“跳过”时的说话层调用另存在题内 `skip` 记录，不覆盖仍待重试的旧回答。
- 判定层与 `tools/interview_eval/pipelines/v3j.py` 逐行对应（同样的 system/user 消息、参数、拼装、verify 触发条件和引擎调用）；Node 桥是新的 `contract_interview_v3j_bridge.js`（常驻一轮判定，操作同评测桥），旧运行合同和旧桥不变。差别只在失败处理：调用失败沿用后端语义（保留原话、显式重试续跑），判定 invalid 时同 v2 一样保留失败、不向老人发问。

### 说话层在后端的做法（与模拟器的差异）

说话层的提示、配置、输入构造、解析、清洗与收尾规则来自 v4d（`speaker-config.json` 的追问上限 2、同一目标 1 次、老人说“不想讲/记不清/累了”即收）。“对话”取自本 session 的消息：入口问题，加上每段回答和它之前老人看到的那条完整消息；判定层记的“原问”与模拟器一样只取问句部分（追问不含承接、转题只取下一题入口、草稿步骤只取固定句）。“已记下”取本题最后一次判定。按用户 2026-10-22 的决定：

| 情形 | 模拟器（v4d） | 后端 |
| --- | --- | --- |
| 追问（引擎 ask / ask_defer） | 说话层写承接 + 问句 | 相同；问句校验不过退回引擎问句（合格的承接保留），调用失败时就是引擎问句 |
| 一题聊完（ready、信息有限，以及老人说记不清、追问到上限） | 收尾一句后直接问下一题 | **保留草稿步骤**：说话层输入与模拟器相同，只取它的承接（去掉“换个话题”“再聊聊”这类转题分句），后接原句“这段可以先整理成草稿了。您还有什么想补充的吗？”并带 `offer_generation`；承接为空、含保存/整理/草稿等词或调用失败时只发原句；之后的补充、核对、保存不变 |
| 明确不想答（“跳过”等控制、引擎 skipped / deferred / limited+declined，以及老人说“不想讲”） | 体谅一句再问下一题 | 相同；失败或校验不过退回 `SKIP_ACK` + 下一题；不出保存入口；模块最后一题时下一项仍是模块菜单 |
| 老人说累了 / 引擎 paused | 先歇，点“继续”后进下一题 | 保持现有暂停：固定句，位置保留 |
| “上次换话题时你说的” | 上一题收尾整句 | 草稿步骤只记它显示过的承接，转题记整句 |
| 下一题 | 会话计划里的 4 道连续题 | 模块内下一题或模块菜单 |

人生骨架（SK 题，走人生概览接口）两种设置下都仍是 v2 判定和原固定话术，本次范围只到访谈入口；sim-hv4d 32 题里有 12 题是 SK 题，后端不会对它们用说话层。是否把骨架也接到 v3j 需要另行决定。

### 验证（全部离线，未花 DeepSeek token）

在 `cloud-deployment/backend` 下运行（测试源码按仓库惯例在 Git 忽略的 `tests/` 里，提交时需 `git add -f`）：

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v             # 后端全部测试：49 项，48 项通过、1 项（需外部冻结记录，原有）跳过
python3 -m unittest tests.test_interview_v3j_full45_replay -v       # full45 后端回放
python3 -m unittest tests.test_interview_v4d_sim_replay -v          # sim-hv4d 说话层回放
python3 scripts/build_interview_v3j_runtime.py --check              # 运行合同与已测原件逐字节相同，输出 manifest SHA
```

- full45：后端新代码逐检查点回放，模型回复按 `Relay.key` 从缓存取（缓存没有就判失败，不会调用）。204 个检查点、259 次请求（判定 204、复核 55）全部命中，结果与 `branch-check-v3j` 逐个相同，评测打分 197/204。
- sim-hv4d：用后端的 `question_turn` / `skip_turn` 按模拟访谈逐轮回放。35 次判定结果、35 次收尾规则动作、33 次说话层输入与模拟器逐字相同，71 次请求全部命中缓存；3 次追问、3 次拒答转题的最终文字相同；27 次草稿步骤与 2 次歇会儿按上表不同（逐条列在测试输出里）。为了对得上，这次回放给后端的是模拟器的“下一题”和“上次换话题”；后端真实值不同的情形（6 处下一题、20 处上次换话题）也列在输出里，它们会产生新的说话层输入，只能用真实调用验证。
- 单元与接口测试（`tests/test_interview_v3j_v4d.py`，18 项）：开关默认 v2、未知值拒绝、启用时启动校验；v2 进行中的题在开关打开后仍走 v2 并复用已存调用、v3j 题回退后仍走 v3j、下一题才换；说话层失败或校验不过的回退；拒答回退固定句与模块菜单；草稿步骤仍带 `offer_generation`；判定、复核、说话层调用在中断后重试都不重复。

### 尚未做

- 阿里云隔离候选环境验证、iPhone 17 模拟器联调：本环境做不了，启用前须按开发约定补做。
- 真实 DeepSeek 调用：未做。后端真实的“下一题”“上次换话题”与模拟器不同的那些说话层输入，以及模块题在真实会话中的整体效果，都还没有真实回复。
- 判定层与说话层的离线成绩仍只来自 45 位开发人物与 8 人 × 4 题模拟，见下文已知风险。

## 合并说明（给合并的人／工具）

- 分支从 `main` 的 `ac9fd10` 拉出，只新增文件，外加本目录和 [第二阶段导航](../README.md) 的一行链接；与 `main` 上其他工作没有重叠路径，正常应可快进或无冲突合并。
- 若 `main` 也改了 `docs/phase-2/README.md`，冲突只在表格最后一行附近：两边的行都保留即可。
- “接入后端”提交块另外修改了 `cloud-deployment/backend` 的 4 个现有文件（`app/services/contract_guided_interview.py`、`contract_interview_state.py`、`interview_modules.py`、`app/schemas/guided_interview.py`）和部署说明；`main` 若同时改了这些文件需要逐处合并，合并后重跑上面的后端测试。
- 每个版本一次提交，标题形如“优化采访链路：<版本> <要点>”，正文写结果与实际执行的验证。按提交顺序合并即可；需要只取到某个版本时，合并到对应提交。
- 每个目录里的主文件（如 `speaker-prompt.txt`）始终是**最新已测**版本；未测版本只放在 `history/`，文件名带 `untested`。
- 不提交：测试集原文、DeepSeek key、缓存、运行结果（都在 Git 忽略的 `.runtime/interview-eval/` 或本机）。

## 迭代记录

- 判定层：[v3 迭代记录 R1–R11](../../prototypes/full-interview-v3/ITERATIONS.md)
- 说话层与模拟访谈：[v4 迭代记录](../../prototypes/full-interview-v4/ITERATIONS.md)
- 怎么复现评测：[评测工具说明](../../../tools/interview_eval/README.md)

## 已知风险

- 判定层的调参与门槛使用同一批 45 位开发人物；10 位留出人物没有金标准，尚未做真正的留出验证。
- 说话层的数字来自 Haiku 盲评的模拟访谈，不等于真人使用；打分器很少给 5 分，以“≥4 分占比”为主要标准。
