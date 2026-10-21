# 当前童年采访三层 AI Prompt 导出

导出日期：2026-10-15。三个 `.txt` 文件是当前工作树 `app/ai/guided_prompts.py` 中三个常量的**逐字内容**，未改写。该源码与阿里云 `shinian-childhood-isolated` 候选容器的对应文件 SHA-256 一致。正式服务 `backend-api-1` 尚无这套三层采访代码；App 默认聊天也尚未启用 `interview_module=childhood`。因此这里记录的是**候选试点版本**，不是当前正式家庭聊天的线上 Prompt。

| 层 | Prompt | 触发时机与输入 | 输出与职责 |
| --- | --- | --- | --- |
| 事件 AI | [01-event-ai.txt](01-event-ai.txt) | 童年模式中收到一轮讲述；输入当前固定题目、当前故事原话、可用的背景原话、之前已核对事实和待答问题 | 返回 `facts`、具体动作 `units`、动作间有证据的 `links` 及经过未知/拒绝状态。只抽取当前故事的事实，不写给用户的回复。 |
| 回答 AI | [02-answer-ai.txt](02-answer-ai.txt) | 只有存在 `pending_question` 才调用；输入该问题的单个目标与接受规则、最新用户原话和当前故事原话 | 判断最新回答为 `answered`、`partial`、`off_target`、`unknown`、`declined` 或 `paused`，附逐字证据。它判断这**一个问题**是否得到回答，不判整件故事完成，也不生成下一个问题。 |
| 模块 AI | [03-module-ai.txt](03-module-ai.txt) | 童年模式确认保存第 5 件及后续新故事时；输入已保存/最低合格数量，以及这些已保存故事的 ID 和原话 | 只指出有证据的疑似重复故事或关键矛盾，并返回对应 `memory_id` 和引文。它不选择新故事、不要求每件事补日期或感悟，也不生成用户话术。 |

## 锁定的故事主线与控制器

本版本在 [`TOPICS`](../../../../cloud-deployment/backend/app/services/guided_interview.py) 中按顺序固定了六个**采访主线**，不是把用户要讲的具体故事内容写死：

1. 小时候家里平常的一天，最记得哪一段；
2. 和小时候一起生活的人，一段记得的相处；
3. 小时候喜欢做的事情中，一次记得的经历；
4. 小时候帮家里做过的事情中，一件记得的事；
5. 童年那些年家里日子的一个变化；
6. 除以上内容外，另一件想留下的童年往事。

**推进权在代码控制器，不在模块 AI。** 控制器根据证据计算当前故事的覆盖情况，选择至多一个预设局部问题；用户可以提前把已讲内容整理成草稿。只有确认保存成功，保存数量才增加并进入下一主线。达到至少 5 件最低合格素材且模块 AI 没报告疑似重复或矛盾时，代码才设置 `chapter_ready=true`。这个标记只是当前规则的结果，不能替代人工判断故事是否丰富；多轮测试已记录过更正事实被误报为矛盾的情况。

## 实际送给模型的消息还包括什么

三个 `.txt` 是固定的角色 Prompt。运行时 `_structured()` 还在系统消息后追加“只返回符合指定 schema 的紧凑单行 JSON”的要求和相应 Pydantic JSON Schema，并把上表中的动态数据放进用户消息。模型输出会经过 Schema 与逐字引文校验；格式或证据不合格时，最多再附一次修正要求重试。动态故事原话、消息 ID、已保存故事和 JSON Schema 随每次调用变化，因此不存在一份对所有请求通用的完整最终消息。

若需要在一份提示词中表达三层规则，可使用[统一版 Prompt](04-unified-guided-childhood.txt)。它以 `task_type` 区分采访轮次与模块复核，并把事件、回答、模块结果放进同一个 JSON 结构。**这是合并导出稿，不是当前后端实际发送的 Prompt**；直接接入运行代码还需要统一输出 Schema、调用入口和证据校验，不能只替换一段字符串。

三层采访之外还有独立的**草稿写作模型**：用户点击整理后，系统仍使用既有写稿 Prompt 生成供核对的第一人称草稿。保存后的童年模式确认语由代码生成，不再额外调用对话模型。这些不计入本导出的“三层”。

源码入口：[`guided_prompts.py`](../../../../cloud-deployment/backend/app/ai/guided_prompts.py)、[`guided_interview.py`](../../../../cloud-deployment/backend/app/services/guided_interview.py)、[`guided_interview.py` Schema](../../../../cloud-deployment/backend/app/schemas/guided_interview.py)、[`llm_client.py`](../../../../cloud-deployment/backend/app/ai/llm_client.py)、[`workflow_service.py`](../../../../cloud-deployment/backend/app/services/workflow_service.py)。
