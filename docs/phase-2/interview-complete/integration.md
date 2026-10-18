# 完整采访算法接入交接

> 最新状态：用户随后明确要求将当前版和新题库立即上线真实后端供人工测试。本次已按该新授权完成v1.29发布，2026-10-18 14:04:11（Asia/Shanghai）生效。此前等待三连轮后才同步的限制，对本次人工测试发布时间被明确覆盖；质量验收本身没有通过，也没有创建验收commit。详见 manual-release-20261018.md 和 evidence/manual-c33-*.json。下文早期探索与计划保留为历史记录。

> 验收顺序纠正：2026-10-18用户要求，三轮均严格>95%之前不得同步云端代码或进行App/模拟器验收。本文件此前的隔离云端与模拟器结果属于提前探索，不作为上线验收依据。正式云端未发布、未commit/push；通过门槛后须重新完成同步前后验证。

上线前还须运行研究工作区 `tools/interview_release_gate.py`，重新审计三连轮原始记录并核对待发布runtime全部文件hash。任一前置检查不通过即停止云端同步、App验证及release commit。

2026-10-18。本记录只说明接入与离线验证，不是三轮真实 DS 验收或生产发布证明。

## 代码与生产基线

- 干净分支：`codex/interview-complete-20261018`，起点 `11e4ed0`。
- 只读核对正式 `backend-api-1` 的 70 个应用／依赖／Dockerfile 文件，其 SHA-256 与此 HEAD 全部相同。主工作树另有 6 个脏后端文件，不应随本次整包发布。
- 当前工作树内 `app/ai/interview_runtime` 是待验收候选的副本，必须在实际部署前换成连续三轮达标的最终冻结原件。不能因为文件已复制就宣称上线。

## 原 App 链路

沿用原有 `/chat/sessions/{id}/life-overview/actions`、`/interview`、`/conversation/messages` 和 `/messages` 路由。没有新增一个 App 不会调用的平行 API。

- 新骨架：SK01–SK06，按原有 `LifeOverview` JSON 外形返回，`total_questions=6`。Swift 题目名称及进度分母同步支持六题。
- 新模块：童年 7、成长 7、工作 13、家庭 7、晚年 6、回望 16，共 56 题；与骨架合计 62 题、193 要素。题目及顺序直接读取冻结合同。
- 新 guided state 版本为 3。每个问题单独保存原话、实际问过的问题、焦点要素、已核验字段、追问次数和原始模型调用记录。切题后不借用其他题的已知资料。
- 仍有未保存内容的旧版本 2 采访继续保留原流程。用户存完旧段、进入下一段时转到版本 3，完整旧 checkpoint 留档；旧 CH/FM 编号不直接映射到新合同里的同名编号。
- 已有七题旧人生概览按旧 schema 读取，不篡改历史原话或确认状态。新人物／从未开始的概览使用 SK 六题。

## 同一算法与调用策略

Python 不重写语义规则。通过 JSON stdin 调用镜像里的 Node，直接载入冻结 JS、合同和通用 prompt。manifest 及其列出文件全部做 SHA-256 校验，缺少发布 pin 时拒绝启用。

每次正常提取固定 A → B。B 无论 A 是否看似通过都执行；B 的代码判断为最终判断，不能挑选得分更高的 A。仅最终结构 invalid 时内部修复一次。仍 invalid 时保留原话及失败原始响应，不向本人重复提问。本人显式重试时可再发起一个有界尝试，所有历史失败仍保存；没有后台无限重试。

每次模型调用成功后先持久化，再开始下一步。A 已完成但 B 网络失败时，原请求 ID 重试只续 B。每个缓存响应绑定冻结 manifest、模型配置、prompt、完整 payload 的摘要，不能用其他回答的响应冒充。最终回复成功后重放同一请求不再调用模型、不重复创建消息。

服务端仍使用发布合同的 `deepseek-v4-pro / thinking enabled / high / max_tokens 16384`，不更改现有草稿和其他功能的默认模型。既有生产 DS 密钥通过现有 `LLMClient` 使用，不另复制或输出密钥。

## 发布配置

Dockerfile 增加 Node 22 阶段，复制 Node 可执行文件到 Python 3.12 bookworm 镜像。无需数据库迁移，状态放在既有 JSON 列。

最终隔离／正式容器必须配置：

```text
INTERVIEW_RUNTIME_DIR=/app/app/ai/interview_runtime
INTERVIEW_RUNTIME_MANIFEST_SHA256=<最终验收候选 manifest.json 的 SHA-256>
INTERVIEW_NEW_SESSIONS_ENABLED=1
```

不设置路径时保留旧默认模式；因此上线验收必须同时核对真实运行环境的 pin 和接口返回的新题目，健康检查不能替代功能验证。

`INTERVIEW_NEW_SESSIONS_ENABLED=0` 只停止新 schema 创建及旧段升级。既有 schema 2 骨架和 guided v3 仍读取相同的已固定 runtime 并可续跑、跨模块，不删除原话。停用新会话时必须保留 runtime 路径与 pin。

回退边界：尚无新 schema 写入时，可以恢复旧镜像。已有新 schema 写入后，旧 `11e4ed0` 镜像不能读取这些状态，不是无损回退方案；应保留兼容版本并前向修复，或先关闭新会话开关。不得自动恢复旧数据库快照而丢掉上线后原话。

原 App 请求上限是 120 秒，生产 Nginx read timeout 是 180 秒，不能覆盖 DS A+B+一次修复的最坏等待。已将采访 POST 请求单独设为 450 秒，其他请求仍为原上限；Nginx 配置例子同步为 450 秒。真实 Nginx 更新由发布者完成，更新前保留原配置回退，不把改了例子称作已改生产。

App 原先已保存稳定请求 ID 和待发输入：骨架将待处理命令保存在本机并从服务端恢复；聊天将最后未配对的用户消息恢复为可重试操作。后台中断后重试会沿用请求 ID。没有另加后台定时轮询或额外自动模型请求。

## 已执行验证

- 10 项纯 adapter 测试：manifest、真实 Node 校验、问题边界、实际提问、固定 A/B、单次修复、网络续跑、缓存摘要、模型参数。
- 9 项旧 API + SQLite 业务测试：62 题目录、SK 六题顺序、原路由、原话先落库、幂等、失败留档、旧段迁移、跨家庭授权，以及关闭新会话后既有 v3 仍可操作。
- 3 项冻结资料等价测试：v1.22 第四轮 21 个 checkpoint 的 `runner.payload_for + model_input` 与 adapter 深度相同（只改变来源标记）；42 份实际 DS A/B 的桥接判断与原始保留 decision 完全相同；历史多轮记录核对 previous_fields 传递。
- 当前真实父集全部 `focus=null`；另有明确标注为合成控制上下文的 focus/target_field_id 传递探针，不把它计为真实人物或模型测试。
- 等价测试发现并修正了 adapter 两处包装差异：补齐 runner 的 `question_contract.material_type`；保留 JSON 字段插入顺序，防止审计数组顺序变化。这两项未修改冻结算法。
- 合计 22 项离线测试通过。只说明代码与保存数据验证，不代表新增 22 次真实模型调用。
- iPhone 17 Pro / iOS 26.0，UDID `8801F7F7-7154-4AEB-88F2-1E77A8393190`：主线 AIMemoirs Debug 构建通过。构建产物 `/tmp/shinian-interview-derived/Build/Products/Debug-iphonesimulator/AIMemoirs.app`，日志 `/tmp/shinian-interview-build.log`。尚未安装运行，也未做真实云端联调。

重跑离线验证（冻结资料在外部研究工作区，故通过环境路径指定）：

```sh
TEST_INTERVIEW_FROZEN_RUN='<完整冻结 run 路径>' \
TEST_INTERVIEW_MULTITURN_RUN='<历史完整多轮 run 路径>' \
python -m unittest discover -s tests -p 'test_contract_interview*.py' -v
```

`tests/` 在仓库已有忽略列表中；仅三个明确测试源码文件已用指定路径加入暂存，未将整个忽略目录加入。

## 发布者仍需完成

1. 用最终连续三轮达标原件替换候选副本，记录 SHA 和真实 DS 验收报告，不在本报告改写旧失败。
2. 用隔离库／独立测试家庭运行实际 DS 原 API 多轮：SK01 不重问已说出生地，FM03 抱怨只算冲突且继续问应对，实际应对之后收口，未知、暂停、重试和下一题正确。
3. 核对所有 62 题目录、运行 pin、模型参数；模拟器连接隔离／正式云端验证实际页面及后台恢复。
4. 备份数据库、媒体、镜像和受保护配置后再发布；保留生产认证 override、媒体卷、端口和现有家庭资料。健康、匿名 401、家庭权限及历史业务只读核对均须执行。
5. 以上验收成立后按用户授权创建 `采访全部流程的完善` commit，并按项目约定正常推送。当前未部署、未 commit。


## 原主工作树重复副本

最初由本任务创建、后续在干净 release worktree 继续修改的两个旧 untracked 文件仍留在 `/Users/student03/Desktop/shinian/cloud-deployment/backend/app/ai/`，未删除或覆盖。2026-10-18 记录其 SHA-256：

- `contract_interview.py`：`d639bc4f10fd98c511c785d4576eb0b69fd88f4b0433027275d33fb4984fa9fd`
- `contract_interview_bridge.js`：`ca53e05fa81204282d966bcd3da7be6feacd90c64974c8d4f7d3c49b4e68a0f1`

最终提交从干净 worktree 创建。以后清理／同步旧副本前须再次核对 SHA 和并发改动，不能整体替换原主工作树。

## 主任务接续验证

- C28 隔离真实模型：首次出生地/村貌回答进入SK02；未知时间也进入SK02且保留unknown；重复相同请求只回放、不重复原话。暂停、恢复及新会话开关均通过。FM03追问语境里再次只说伴侣抱怨，仍保留E2缺项，没有把要求当已应对；目前尚未补入实际应对完成烟测。原始公开报告 `evidence/c27-c28-isolated-smoke.json`。这些为合成场景的实际API测试，不计55人物成绩。
- iPhone17Pro已安装运行，通过隔离云端18010恢复至第2题/共6题，原文“时间记不清、小医院、村貌”可回看。截图在evidence目录。
- 独立代码复核发现未完请求后发送新回答会导致原请求无法重试。Root已用原API合成provider重现502→双向不可恢复，改为写入新消息前拒绝409，保留原请求；重试只续B，完成后新内容可正常发送。12项业务测试通过；adapter与frozen parity待最终冻结runtime换包后合跑。
- 当前智能体受到平台额度限制，后续由主任务执行。正式云端尚未改，尚无commit/push。
