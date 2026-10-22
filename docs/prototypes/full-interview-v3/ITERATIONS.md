# v3 采访判定链路迭代记录（第二阶段）

目标：45 位开发人物 full45（204 关键点）关键点准确率 > 95%（≥194/204）。
约束：只做对未见人物同样成立的通用改进；不按人物/题例写规则；不把金标准或人物原话写进提示或代码；
正式链路 deepseek-v4-pro、thinking disabled；严格省 token（只改代码用 --offline 回放）。

## 0. 接手时状态（2026-10-21）

- 已有缓存：v3d 判定提示 × full45 全部 204 点（`full45-v3d`）；v3f 判定提示 × hard66 69 点（`hard66-v3f`）。
- 上一任留下 `pipelines/v3g.py`（v3_judge + 未测试的 verify 阶段，`V3_EXP=noverify` 可关闭；`V3_JUDGE_PROMPT` 可回放别的判定提示）。
  其离线实验：`off-f45d-g0` 182/204；`off-f45d-g0-link_span` 183/204（+SK06）；`model_subject` 无净收益（+SK04 −LT04）。
- 累计已发 DS token（tokens.py）：约 2,038,841。
- v3d 回放（link_span）在 full45 的 21 个失败全部落在 hard66 内；v3f 在 hard66 上比 v3d 多过 7 个、少过 4 个（SK06、FM05、SK03c、SK03d）。

## 迭代

### R1（只改代码，0 token）— 新管线 `pipelines/v3h.py`（自 v3g 复制）
- link_span 默认开启：带 link 的解释项，若前一句含所选 link_word，则并入 value。
- 主体规则：合同首个主体为 self 时默认 self；首个主体不是本人（parents/family/teacher 等，共 6 个字段）时采用判定所选的允许主体。
  理由：以本人为首的字段，其他主体多是“对象/受众”（如 younger_generation），判定容易混淆；以他人为首的字段，判定在几个他人角色间的选择有信息量。
- 结果：`off2-f45d-h0`（v3d 判定缓存）184/204；`off2-h66f-h0`（v3f 判定缓存）53/69（均 +SK04，无回退）。新发 token 0。

### R2（只改代码，0 token）— “现在”阶段回退
- 规则：要求阶段=现在的字段，判定为 known 但引擎因所选句不在“现在”框架内（如处于“以后打算”框架）而降为 ambiguous（provenance=required_stage_not_grounded）时，
  改用同一来源证据里离所选句最近、本身含“现在/最近/目前…”的句子作 value 重提一次；只有引擎接受为 known 才采用，否则保留原结果。
- 结果：`off2-f45d-h1nf` 185/204；`off2-h66f-h1nf` 54/69（均 +LT01b-df0，无回退）。新发 token 0。

### R3 — 接入 verify 阶段（v3h 重构）
- 设计：verify 只核对“引擎实际会记录为 known/none/ambiguous”的字段；输入只含这些目标的标准与将被记录为证据的句子（含原问、阶段要求、父项说明“可以是同一句话”）。
  输出 says/words/direction/itself；itself=no → missing；direction 与判定不同且状态允许 → 改状态；然后代码重新组装（不再发调用）。system 提示静态。
- verify 提示 v1（`history/verify-prompt.v1.txt`）：原则式（满足任一情形即 yes；属于该类即 yes；相近概念 no；靠推测 no；主体/阶段/说明不符 no；先否定后讲一般道理仍 negation）。
- run `h66-v3h-v1`（v3f 判定缓存 + verify v1）：57/69（+LT05b、LT05-fe7、SK03d、CH06b；−SK03-E1“大家庭同住”被误拒）。56 次新调用，新发 token 57,467。
- 未修好：RV02“有遗憾但没说是什么”仍判 content；RV09c、SK03c、WK12、GR03-E2、CH03b 这类“靠推测得出的认定”verify 仍判 yes——单纯的 yes/no 核对对“推测”不敏感。
- run `h66-v3h-v2`（verify 提示 v2，`history/verify-prompt.v2.txt`）：60/69。新发 token 63,117。
  v2 改为“改写检验”：先写 answer（受访者只凭原话会怎样回答该目标的问法），再写 added（answer 中原话没说、靠推想加上的关键判断），added 非空 → itself=no。
  相对 v1：+RV09c、SK03(E1 恢复)、SK03c、GR03、CH03b；−LT05b（同一条目在 v1/v2 间翻转，边界项）、−GR07（把“升学报考想学什么”判成没说离校规划，误拒）。
  风险：v2 中“目标名称含本人认定/改变/影响…必须本人说出这层认定”一句会误拒 WK05/WK09 这类金标准宽松接受的条目（full45 中约 10 个此类 known 字段在 hard66 之外）。

### R4 — 判定提示 v3i（合规修订）+ verify 提示 v3
- 合规审查：v3f 判定提示的 negation 示例“也不希望别人记住什么”是某位开发人物的原话；“不分家”“流亡”“河”“报考”“机会被别人抢走”等是从金标准/失败例直接取的字面词。
  v3i 全部改为通用表述（如“没什么特别想让人记住的”“跟哪些家人同住、大家庭一起过日子”“逃难、战乱、失业、家道中落”“山水、街道、房屋”“毕业或升学时打算报考、学习或从事什么”“机遇得失”）。
  另加两条通用规则：先明确否定、后面只讲一般道理仍是 negation；问“有没有……”只答“有”或只泛泛议论属于 affirmed_unspecified。
  代码：条件子项说明加“（可以是同一句话）”（判定与 verify 两处）。
- verify v3：删去“名称含本人认定…必须明说”一句（过严）；unspecified 增加“问有没有只答有”的通用规则与虚构例；
  yes 类别例增加“毕业或升学时打算报考/学习/从事什么属于离校时的规划”；“具体往事”补充“一贯的职责/工作目标/做人原则而没有某一次发生过的事”与虚构例。
- run `h66-v3i-v3`（判定 v3i + verify v3）：55/69，新发 token 224,036（判定 69 次全部新发 + verify）。
  判定 v3i 单独（离线 `off2-h66i-nov`，noverify）56/69，对比 v3f 同条件 54/69：+FM05（“可以是同一句话”）、+SK03c、+CH06b，−LT01-a06 t0（core 选句变化）。
  针对性的两条判定新规则（先否定后讲道理仍 negation；“有没有”只答“有”）在判定端都没生效（LT05-fe7、RV02-wdj 判定仍为 content）。
  verify v3 明显变差：新增的“问有没有只答有不算内容”使复核员把许多正常回答判成 unspecified+“没说”而拒收（误拒 LT01b-f522、FM05、WK09、SK03-E1）。结论：v3 作废，verify 回到 v2。
- run `h66-v3i-v2`（判定 v3i + verify v2，verify 多数命中缓存）：59/69，新发 token 4,862。

### R5（只改代码，0 token）
- 阶段字段 value 放宽（stage_wide，默认开）：要求阶段的字段先用 core∪units 的连续句段作 value；若引擎因阶段无法落定（required_stage_not_grounded）或语义拒收，
  再退回只用 core（原做法）。离线：v3d 缓存 full45 185→186、v3i 缓存 hard66 56→57（均 +LT01-a06 t0），v3f 缓存不变，无回退。
- verify 改向（direction）后的依据句：改为 none/ambiguous 时，证据并入复核员实际读到的句子（此前只用判定的 units，导致“先否定的那句”不在证据里被引擎以 negative_without_explicit_basis 拒收）。
- 结果：`off3-h66i-v2b`（v3i 判定 + verify v2，全缓存）61/69（+LT01-a06、+LT05-fe7）。新发 token 0。
- hard66 剩余 8 个：LT05b（工作目标当往事，verify 边界翻转）、GR07（verify 误拒）、RV02-wdj01（“有遗憾”未判 unspecified）、WK12（金标准偏严，可争议）、
  WK05-434 / WK05-133 t1（所选句与金标准片段不同）、RV02-wdj02 / LT01b-a06 t1（上限测试也过不了：引擎语义守卫/阶段证明）。

### R6 — full45 真实全量（判定 v3i + verify v2 + R1–R5 代码）
- run `f45-v3i-v2`：189/204 = 92.65%，新发 token 437,529（判定 132 + verify 等共 238 次新调用；hard66 部分命中缓存）。
- 拆解（离线回放同一批真实结果，0 token）：判定 v3i 单独（`off3-f45i-nov`）188/204，已高于 v3d 回放（186）。
  verify v2 在 full45 上 +7（LT01-f522、LT05-fe7、RV09c、SK03d、FM03、GR03、CH03b）−6（LT06、GR07、RV06b、SK03c-2c29、RV12、CH06 均为 hard66 以外的正确条目被误拒），净 +1。
  结论：verify 作为“拒收过滤器”在边界条目上近似随机（“没说”类拒收 4 对 4 错，“推想 added”类 2 对 3–4 错），在未参与调提示的 135 个点上误拒约 4.5%，不能泛化，不采用拒收。

### R7（只改代码，0 token）— core 守卫探测（guard_probe）
- 问题：value 取 core∪units 的整段后，引擎为“短答案”设计的语义守卫（如投诉/要求≠应对、职业事实≠责任与自我安排）被邻句稀释而不触发。
- 规则：对每个将记录为 known 的字段，额外用 value=evidence=判定 core 句探测一次引擎；若引擎在这种形态下语义拒收，则该字段不记录。
- 结果：v3d 缓存 full45 186→187（+WK12）；v3f 缓存 hard66 54→55（+WK12）；v3i 缓存 full45 188→189（+FM03）。三套缓存均无回退。默认开启。

### R8（0 token 离线实验）
- 多提示投票：v3d/v3f/v3i 三套判定在 hard66 上逐目标多数票（`off5-h66-m3-*`，3 种平票顺序）56–57/69，不高于 v3i 单独 57/69 → 错误是系统性的，放弃（与上一任的采样投票结论一致）。
- verify 只用“改向”不拒收：所有方向都采纳时 187（复核员把“没说”标成 unspecified，会把正确 known 改成 ambiguous）；只采纳 negation 方向 → 190/204。
- 最终 verify 用法：仅当被记录字段的证据句含明确否定词（没有/不希望/不想/没什么/不需要/无悔/不后悔）时才调用（full45 56 个关键点），只采纳 known→none，
  none 的证据并入复核员读到的句子。`off6-f45-final` 190/204；`off6-h66-final` 58/69。

## 第三棒（2026-10-21 晚起）

接手核对：当前默认链路是 `pipelines/v3h.py`（不是 v3_judge.py；v3_judge.py 为最早的 v3）。v3h 默认开关：link_span、主体规则、now 回退、stage_wide、guard_probe 全开；
verify 仅在被记录字段证据含明确否定词时调用、只采纳 known→none；judge-prompt.txt = v3i，verify-prompt.txt = v2。离线复现 `off9-f45-base` 190/204。
累计 DS token（tokens.py）接手时 2,826,987；本棒预算 ≤ 80 万。
为保留 v3h 可复现性，本棒改动放在新管线 `pipelines/v3j.py` + 新运行时目录 `docs/prototypes/full-interview-v3j/`（自 v3 复制；判定/复核提示逐字不变 → 已付费缓存全部命中）。
回归检查固定用 4 套已付费缓存的离线回放 + oracle：f45i（v3i 判定+verify，基线 190）、f45d（v3d 判定，基线 187）、h66f（v3f 判定，基线 55）、h66i（v3i，基线 58）、oracle（基线 199）。

### R9（只改代码/引擎，0 token）
1. 引擎 `semantic-targets.js` 的“定义≠本人经历”守卫（concept_definition_not_owned_experience）对“说不出来/难以言说/一言难尽…”让路。
   理由：这类话是本人对自己经历“有但说不出”的陈述；引擎自己的 onlyExistentialExperience 已把“说不出来/难以言说”列为“有、但未辨认”（→ambiguous），
   定义守卫原先会把它当作对概念下定义而整条拒收，两条规则互相矛盾。对任何受访者都成立。
2. 管线：逐字类字段（place/time/duration/life_summary/period）的 value_text
   - 在受访者原话里（含繁简映射）根本找不到 → 不记录该字段（多为从原问抄来的词，如原问里的“小时候”），不再退回整句当值；
   - 能找到但不在判定自己给出的 core 句里 → 以 core 句为准（判定的答案句与抄写的片段自相矛盾时信答案句）。
   4 套缓存中逐字字段共 45 个，除这 2 种异常外全部“片段在 core 内”，规则不影响它们。
3. 引擎 `engine.js` 的“生活条件≠相处氛围”守卫补词：生活/条件…后接“好/很好/苦/穷/宽裕/艰苦…”这类普通好坏评价也算生活条件；
   同时把“待人/对待/孝顺/体贴/疼爱/感情/矛盾…”补进“已讲到人际相处”的豁免词（否则会误拒“家里生活比较好，母亲待人非常好…”这类真正讲到相处的回答，CH06 即此例）。
- 结果（off10-*-j3b）：f45i 190→193（+RV02-02、+SK01c、+SK03d）；f45d 187→188；h66f 55→57；h66i 58→60；oracle 199→200。四套缓存与 oracle 均无回退。新发 token 0。

### R10（只改引擎，0 token）— 同题“兄弟目标”分离守卫
- 观察：剩余误收大多是“同一题里相邻的两个目标被互相顶替”，而合同本身已把它们拆成兄弟目标：
  CH03-E1 疼爱本人的亲人 / CH03-E2 影响深的亲人；RV09-E1 吃苦、E2 努力 / E3 运气；GR03-E1 影响本人的老师 / E2 本人认定的改变；
  LT05-E1 希望被记住的做事待人方式 / LT05-E2 希望被记住的一件故事（合同原文：“泛泛工作职责、服务目标或通常做事方式不是一项具体故事”）。
  判定提示里早已写明这些相近概念排除，但单次多目标判定仍会顶替（第二棒已证实 verify 拒收在边界上近似随机）。
- 规则（`full-interview-v3j/semantic-targets.js` 的 SIBLING_GUARDS，按 semantic_role 生效，原问并非直接问该目标时才检查）：
  证据只出现兄弟目标的概念词、且没有本目标自己的概念词 → 语义拒收（retained missing）。
  - influential_relative（CH03-E2）：有疼爱/照顾类词，却没有“影响/改变/榜样/教我/学到/一辈子/难忘/性格/像他…”；
  - luck_view（RV09-E3）：有努力/条件/天赋/机会/把握类词，却没有“运气/幸运/命/老天/缘分/碰巧/赶上/可遇不可求…”；
  - narrator_change_effect（GR03-E2、CH07-E2）：有怀念/感谢/敬佩/优秀/教导类评价，却没有“改变/影响/与…有关/让我/教我/学到/养成/从此/爱上/至今…”；
  - selected_identifiable_story（LT05-E2，原合同已声明该角色但没有守卫）：有职责/服务对象/一贯做法类词，却没有“那次/那年/当时/第一次/最早/×年/开展/获得/完成…”等一次性事件标记。
  角色写入 `contracts.json` 的 semantic_role 与 `semantic-roles.json`（judge/verify 的输入不含 semantic_role，已付费缓存不受影响）。
- 防过拟合：词表按合同概念写成同义词族，不含任何受访者原话；先用 oracle 发现初版“改变”守卫会误拒“我对死亡已麻木”这类以结果状态表达的影响（CH07），
  于是把该守卫的触发条件收窄为“只有对来源人物的评价/怀念”；另用 23 条自拟正反例（非语料）单测，修正后全部符合预期（“可遇不可求”“碰上”算运气，“她教我做人…”算改变）。
- 结果（off10-*-j4c）：f45i 193→197（+RV09c、+LT05b、+CH03b、+GR03）；f45d 188→191；h66f 57→61；h66i 60→64；oracle 200（不变）。四套缓存均无回退。
  noverify 对照 196 → 否定复核仍净 +1（LT05-fe7），保留。新发 token 0。
- 注意：GR03 因 E2 不再被记录，verify 的输入变化，形成 1 个缓存未命中（真实运行时会新发 1 次 verify 调用）。

### R11 — full45 真实确认（v3j）
- run `f45-v3j-final`：**197/204 = 96.57%**（gate_strictly_above_95 = true）；有原话要素 174/179，追问 198/204，漏提 2，误收 2，协议无效 0。
  模型调用 新发 1 / 缓存 258；新发 token 1,087（即 R10 预告的 GR03 那 1 次 verify）。与离线 `off10-f45i-j4c`/`j5` 逐点一致。
- 本棒新发 token 合计 1,087（R9/R10 全部离线）；累计（tokens.py）2,828,074。
- 剩余 7 个失败：判定选错句/漏提 4 个（LT01b t1 选了第一段“练气功”而没用第二段“乐趣”问答；FM07-E2“这句话使我太感动了”漏判；
  RV02-01“不后悔但有遗憾”判 content；WK05-434 选了“年轻人的想法”而非选择本身“这样开出去”）；可争议金标准 3 个（LT01-f522、WK12-E2、WK05-133 t1）。
- 生产成本：每关键点 1 次判定（约 2.3k token），约 27% 的关键点再加 1 次否定复核（约 1.2k）；无修复调用。
