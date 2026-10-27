# 采访 → 成书层 交接规格 v1

本文规定采访交给“成书层”的数据：成书层只读这一份数据，按六模块分章写成抒情回忆录。机器可读的定义见 [handoff.schema.json](handoff.schema.json)；原型的构造代码见 `tools/memoir_eval/inputs.py`（测试素材）。

## 1. 原则

- **原话是唯一的事实来源。** 每题老人说的每一段话（全文 + 当时 App 显示的问句）都要交给成书层；成书层写的每一句都标出依据的原话编号，代码核对数字、年份、人名地名必须出现在原话里。
- **如实草稿是已确认的事实整理**（GROUNDED_DRAFT_PROMPT 产出、老人看过保存的那一版）：成书层用它理解事实，核对不过时退回它，但不从草稿里取原话之外的事实。
- **状态比文字优先。** 字段状态 unknown（记不清）、declined/deferred（不愿讲/以后讲）、题目被跳过，都要随数据一起交过来；成书层据此写“记不太清”、不写不愿讲的内容。
- **私事默认不写**：疾病、家庭矛盾、他人隐私，以及老人/家人标为“不写进书”的内容，单列待确认。
- 不做多模态：照片不进成书层（PDF 里照片仍按现有设置排）。

## 2. 交接数据一览

| 字段 | 内容 | 成书层怎么用 |
|---|---|---|
| `person` | 老人 id、姓名、与记录者关系 | 第一人称“我”始终指老人 |
| `material` | 素材概况：原话总字数、题数、来源、快照哈希 | 选篇幅档位；判断成书版本是否过期 |
| `catalog` | 题库版本（冻结 83 题）+ 题目分类文件 | 题号 → 模块、故事/事实/感悟 |
| `skeleton` | 开篇骨架 SK 11 题的题号与骨架状态 | 序章素材 |
| `questions[]` | 每题：题号、模块、分类、问句、状态、memory/session id、日期地点 | 规划分章分节 |
| `questions[].turns[]` | 老人每段原话全文 + 当时显示的问句（入口问句或追问）+ 时间 | 唯一事实来源；成书句子引用的编号 |
| `questions[].fields` | 判定层字段：label、state（known/none/unknown/declined/deferred…）、value、evidence | 记不清、不愿讲、已知事实的边界 |
| `questions[].draft` | 已确认的如实草稿：标题、段落 + 每段原话来源；是否手改、memory.version | 理解事实；核对失败的退回文本 |
| `questions[].markers` | 记不清 / 不愿讲的原话句子（字段状态 + 代码匹配） | 写“记不太清”；不愿讲的句子从素材中剔除 |
| `questions[].time_clues` | 代码提取的时间线索（年份、民国纪年、年代、岁数、“小时候/后来”） | 章内按时间排序 |
| `voice` | 老人实际用的称呼（我爸/父亲…）、自称、口头语 | 保持老人口吻 |
| `excluded_values` | 老人更正后作废的旧说法 | 从原话中剔除，不写旧说法 |
| `private_flags` | 标为不写进书的内容（需新增，见缺口 G4） | 不写，列入待确认 |

题目分类（用户 2026-10-26 确定）：23 道故事题 = 成书主干，一个故事一节；23 道事实题 = 背景与过渡；37 道感悟题 = 引语与章末回望（能对应前面经历的拆到那一章章末，最后一章只留真正的收尾）。分类文件随原型存一份：[question-depth.json](question-depth.json)（来自 interview/claude-story-deepen 分支 `docs/prototypes/full-interview-v5/story-questions.json`，v5a）。

## 3. 从现有后端到交接数据的映射

现状（origin/main 6b28aa7）：**一题 = 一个采访会话 = 一段回忆**。老人在 App 里答完一题、确认草稿后，`confirm` 把会话标为 completed，写入一条 `memories`；下一题开新的会话（`open_person` → `following()`），上一题的题目状态随引导状态带到新会话。

| 交接字段 | 现有来源 | 说明 |
|---|---|---|
| `person` | `family_members`（id、name、relationship） | |
| 一位老人的全部回忆 | `memories where family_id=? and primary_person_id=?`（同 `memoir_service.snapshot`） | 只取现存回忆；已删除的不出现 |
| `question_id`、`module` | `memories.information.guided_interview.contract_state.question_id`；模块 = `guided_interview.module`（或题号前缀 CH/GR/WK/FM/LT/RV） | 保存时 `MemoryCreate.information = session.information`，引导状态随之写进回忆。**旧版自由聊天回忆没有 guided_interview**，见缺口 G1 |
| `turns[].text` | `contract_state.sources[]`：`{id(=chat_messages.id), text, question_id, speaker, question}` | 也可从 `chat_messages where session_id=memory.source_session_id and role='user'` 取（= `_build_raw_content`），但 sources 带了每段对应的问句 |
| `turns[].asked` | `contract_state.sources[].question`（App 当时显示的最后一条助手消息） | v2 与 v3j_v4d 两条流程都有 |
| `turns[].created_at` | `chat_messages.created_at` | |
| `fields` | `contract_state.fields`（v2）/ 同结构（v3j_v4d），`last_result.effective` 为生效状态；label 取运行包 `contracts.json` 的 `elements[].label` | 状态集合：missing/known/none/unknown/declined/deferred/ambiguous/conflict/not_applicable |
| `status` | saved：存在 memory；skipped：`guided_interview.processed_topics[qid]=='skipped'`；limited：生效状态里有 unknown/declined 但已保存 | |
| 跳过的题的原话 | 最新会话的 `guided_interview.contract_history[qid]`（`following()` 把每题的 contract_state 原样归档）；切换模块时在 `module_checkpoints` | 见缺口 G2 |
| `draft` | `memory_drafts.payload._evidence`（`session_id` 唯一）：`title.text/sources`、`paragraphs[].text/sources(message_id, quote)`；手改后 `_evidence=None`、原证据在 `_original_evidence`，`_manually_edited=true` | 保存后正文 = `memories.summary`；回忆详情里再改会提升 `memories.version`，以最新 summary 为准（见缺口 G3） |
| `memory_date`、`location` | `memories.memory_date`、`memories.location` | 只用于排序参考，不覆盖原话 |
| `markers` | 字段状态 unknown / declined / deferred（+ 引擎记录的原话 value）；再由代码在原话里匹配“记不清/不记得/想不起/不想讲/不多讲”等 | `contract_v3j` 的 declined_partial（答了一部分又说不想多讲）：答过的部分可写，不想讲的那句剔除 |
| `excluded_values` | `memories.information.excluded_values` | 旧版自由聊天流程的更正记录 |
| `skeleton` | `family_members.life_interview`：schema_version 2 时 `questions[qid]`（与正题同构：sources、fields、status、last_result），状态在 `status`；schema_version 1（旧 7 话题 home/learning…）只有 `fields[].evidence` | 序章素材；旧 7 话题按 topic → 模块映射（home→childhood、learning→growth、early/later_work→work、family→family、changes/present→later_life） |
| `voice`、`time_clues` | 成书时由代码从原话提取 | 不需要后端存 |

## 4. 缺口：后端需要补的

- **G1 题号没有显式列。** 题号只埋在 `memories.information.guided_interview.contract_state.question_id` 这个 JSON 里，且只在引导采访（version 3）里有；旧版自由聊天的回忆没有题号。建议 `memories` 加 `question_id`、`interview_module` 两列（保存时写入，迁移时从 information 回填），旧回忆为空时由成书层按内容归章（原型里就是这样处理测试素材的，见 §5）。
- **G2 跳过/拒答的题没有独立记录。** 跳过的题不生成 memory，原话和状态只活在“最新会话”的 `contract_history` 里，换模块后在 `module_checkpoints`；会话被删或状态被覆盖就丢了。建议加人物级的“题目台账”（例如 `interview_answers` 表：person_id、question_id、status、sources、fields、memory_id、updated_at），保存/跳过时写入。成书层与“采访进度”都读它。
- **G3 草稿与正文的对应。** `memory_drafts.payload._evidence` 给了段落来源，但保存后在回忆详情里改正文（`memories.version` 增加）就没有来源了。成书层规则：以最新 `summary` 为老人确认的事实文本；正文改过时，把改后的正文也作为一条“老人确认的补充原话”交给成书层（source_id 另编），并把被删掉的旧事实列进 `excluded_values`。后端需在编辑回忆时保留“改前/改后”或至少记录 `edited_after_save=true`。
- **G4 “不写进书”的标记没有地方存。** 私事默认不写，但需要老人/家人决定。建议成书版本表里存 `exclusions`（source_id + 原话片段 + 类型 + 决定），见 README 接入方案。
- **G5 骨架与正题分开存。** 骨架在 `family_members.life_interview`，正题在会话里；交接时需要合并读。旧版 7 话题骨架没有题号，只能按话题映射到模块。
- **G6 内容快照哈希。** 成书版本要知道素材是否变了：沿用 `memoir_service.snapshot` 的 `content_revision` 思路，对交接数据算哈希存进成书版本，素材变化时提示“有新回忆，可重写某章”。

## 5. 原型里的测试素材怎么构造（tools/memoir_eval/inputs.py）

- **富素材**：测试集 45 位开发人物的公开访谈摘录（`.runtime/interview-eval/testset/excerpts.jsonl`）。摘录的 `question_ids` 全为空，所以**按内容归题**：每人一次 DeepSeek 调用（`prompts/classify.txt`），把每段摘录归到 83 题中最贴切的一题（一段只归一题、不拆段；讲具体经过优先归故事题、讲道理归感悟题、只交代背景归 SK；时期按原话里的年龄年份判断）。代码校验题号合法、每段恰好一次，未归题的落到 RV16 并记录。带 `provenance-warning.json` 中 `do_not_use_entire_excerpt_without_manual_clipping` / `exclude_from_self_evidence_for_catalog_narrator` 标记的摘录整段不用。繁体转简体用运行包的 OpenCC 字表。**不读金标准**。
- **薄素材**：已有模拟访谈运行里模拟老人说的话。只取真实运行（不取 off-* 回放、dry、smoke），每题取最新版本的运行（st6 > st5 > sim-h*），带运行结束时的字段状态。
- **如实草稿**：测试素材没有老人确认过的草稿，用生产的 GROUNDED_DRAFT_PROMPT（加上 App 引导采访附加的那段要求）每题生成一版，视为已确认。调用失败的题用原话本身作草稿（不编）。
