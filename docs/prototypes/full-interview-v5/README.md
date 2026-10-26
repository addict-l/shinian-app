# v5 故事题深挖（模拟器原型，未接入后端）

2026-10-26。用户要求：“先对故事题做一下测试，看看采访是不是自然的深挖。”成书需要更厚的素材，v4d 每题老人平均只讲约 47 字，要素齐了就收。
本目录在 v4d 之上只加一步：**故事题在要素已齐之后、收尾之前，最多再问 2 次细节**（敏感题 1 次）。其余 60 题、判定层、v4d 说话层提示、量表都不变。
方案出自《故事题清单》；23 道题的选择、敏感题只问一次、短答门槛与 2 次上限都按默认值执行，**用户已于 2026-10-26 确认**。后端候选见 `INTERVIEW_PIPELINE=v3j_v5f`（`cloud-deployment/backend/app/ai/interview_story.py`，交接单在 `docs/phase-2/interview-optimization/handoffs/`）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `story-questions.json` | 冻结 83 题的深度标签：故事 23（含深挖方向、敏感标记）、事实 23、感悟 37。题库本身不改 |
| `deepen-prompt.txt` | 深挖问句的独立说话层提示，**当前为 v5f**（v5e1 + ack 可带一句心疼的话）：以写回忆录为导向挑线头（优先有下文的人、事、转折）、部分记不清时顺着接着讲的问、一次只问一样、不预设、不复述 |
| `speaker-prompt.txt` | v5 说话层提示（追问 + 收尾，**v5f**）：不复述不总结、收尾一句温和的短话接住一个具体的人或事（讲到苦处可以心疼一句）、转题可以用“那咱们再聊聊 / 说起……”但同一场谈话换着说。v4d 的 `../full-interview-v4/speaker-prompt.txt` 不改 |
| `speaker-config.json` | **v5f**：v4d 配置 + `deepen` 块（含 v5f 的 `no_yes_no`、`no_repeat_last`）+ `speaker_prompt`、`signal_scope`（记不清但接着讲）、`echo_guard`/`template_guard: "repeat"`/`echo_fragment_chars`/`echo_names`/`echo_fragment_bare`（去复述、转题短语只限同会话重复）、`short_chars_first`。后端运行合同 `interview_runtime_v3j_v5f` 逐字节复制本目录的提示、配置与题标签 |
| `material-prompt.txt` | 回忆录素材价值量表（Haiku，只看老人原话，`tools/interview_eval/simulate/material.py`） |
| `history/` | v5a–v5e1 各版提示与配置（迭代组运行用的就是这些文件） |
| `story-plan.json` | 故事题测试的会话计划（`tools/interview_eval/simulate/plan_story.py` 生成） |
| `ITERATIONS.md` | 迭代记录与运行结果 |

## 结果（定版：迭代组 v5c + 留出组 v5c1，对照 A = v4d）

| 故事题 | A（v4d） | B（深挖） |
| --- | --- | --- |
| 老人原话 字/题 均值（中位） | 54.3（52） | 68.0（53） |
| 每题深挖次数 | 0 | 0.43（21 题中 6 题深挖，共 9 次） |
| 自然 ≥4 | 76% | 82% |
| 时机 ≥4 | 100% | 97% |
| 硬性违规（轮） | 2/25 | 1/34 |

原话字数升了 25%，离 150 字/题差很远：模拟老人每次正常回答按设定只有 30–100 字，且 71% 的故事题按规则不挖（首答很短、记不清、不想讲）。自然度、违规达到目标，时机差 1 条（已由 v5c1 守卫修掉）。细节与逐条阅读见 ITERATIONS。

## 第六阶段结果（定版 v5e1：迭代组 v5e + 留出组 v5e1，对照 A = v4d，21 道故事题）

| 故事题 | A（v4d） | 定版 |
| --- | --- | --- |
| 复述率 / 其中收尾 | 64% / 61% | 38% / 13% |
| 套路率 | 61% | 6% |
| 老人原话 字/题（中位） | 54.3（52） | 102.3（97） |
| 素材条数/题（Haiku） / 可写性 ≥4 | 3.57 / 24% | 4.86 / 38% |
| 自然 / 贴合 / 时机 ≥4 | 76% / 96% / 100% | 78% / 69% / 89% |
| 硬性违规（轮） | 2/25 | 5/45 |

素材与去复述达到目标；贴合、时机、违规没有达到“不低于 A”（收尾承接与深挖第二问），留出组自然度也低于 A。详见 ITERATIONS 第 6 节。指标：`style.py`（复述率、套路率）、`material.py`（素材价值）、`scope_impact.py`（信号读法影响检查）。

## 第七阶段结果（v5f 温暖，迭代组 5 人 15 道故事题，只调一轮）

| 故事题 | A（v4d） | v5e | v5f |
| --- | --- | --- | --- |
| 自然 / 贴合 / 时机 ≥4 | 74% / 95% / 100% | 85% / 70% / 91% | 86% / 79% / 97% |
| 硬性违规（轮） | 2/19 | 3/33 | 2/29 |
| 复述率 | 60% | 32% | 23% |
| 老人原话 字/题 · 素材条数/题 | 58.7 · 3.87 | 109.3 · 5.00 | 82.3 · 4.67 |

自然、时机回到 A 的水平，复述仍远低于 A；贴合 79% 未到参考的 85%，字数与素材低于 v5e（深挖守卫拦下 3 次深挖），原因与逐条阅读见 ITERATIONS 第七阶段。

v4d 的 `speaker-prompt.txt`、`simulator-prompt.txt`、`sim-config.json`、`scorer-prompt.txt`、`split.json` 仍在 `../full-interview-v4/`，本阶段原样使用。

## 深挖规则的实现（`tools/interview_eval/simulate/interview.py`）

1. **何时考虑**：只在故事题上，且本题按 v4d 收尾规则判为 `done`（引擎 ready、老人没说不想讲）时。其余收尾（记不清、不想讲、追问到上限、信息有限、累了）一律不深挖，记录 `not_done_<原因>`。
2. **不问的情形**（代码门槛，记录原因）：已问满（`cap`，敏感题 1 次、其余 2 次）；本题老人回答已 6 次（`max_turns`）；老人上一句去掉标点 ≤20 字（`short`）；上一句有 C01 规则认出的“记不清 / 不想讲”（`signal_unknown` / `signal_declined`；“累了”在此之前已按休息处理）；本题老人原话合计 ≥300 字且字面上已有场景、人物、细节、感受中的三样（`detailed`，粗略的字面标记，只作门槛用）。
3. **问什么、怎么问**：单独一次说话层调用（`deepen-prompt.txt`，deepseek-v4-pro，thinking disabled，与 v4d 同参数），输入为话题、深挖方向、敏感标记、本题对话、已深挖过的维度；输出维度 + 承接 + 问句。模型也可以判断不必再问（`model_skip`）。
4. **校验**：v4d 追问的校验（只有一个问号、问句 4–60 字、承接 ≤40 字、无系统词和夸赞、不重复问过的话）+ 不含推断词、不含“细节/回忆录”、不出“是……还是……”、维度合法且不重复；承接先过 v4d 的 `clean_ack`，只有承接不合格时去掉承接保留问句。
5. **失败**：调用失败、模型不问、校验不过 → 不深挖，按原来的收尾走（v4d 收尾说话层）；不回退成固定问句。
6. **老人对深挖的回答**：不再调判定（`rejudge_answers: false`），原话记进本题的 `deepen_sources`（带问句与维度）。理由：本题要素已齐，深挖回答是写书用的细节，不是新要素；再判定一次约 2.2k token，且可能把已齐的要素改判成冲突或引出新的追问，与“问完细节就收”相悖；后端接入时这些原话作为本题来源进入草稿即可。
   回答里有“累了”或暂停 → 休息；“不想讲” → 按已答收尾（`declined_partial`）；“记不清” → 收尾时体谅一句（`unknown`）；“跳过” → 已答收尾；其余再过一遍第 2 条的门槛决定是否再问一次。
7. **承接与守卫**（v5c / v5c1）：承接的实词全部又出现在问句里时去掉承接（`drop_echo_ack`）；一句里逗号分开的两段各带疑问词即判“一句两问”（`multi_part`）；老人说“想不出 / 说不出 / 没什么特别”也不再深挖、承接带“有意思 / 真好 / 难得”即去掉（`extra_guards`，只作用于深挖，v4d 与后端共用的 `elder_signal` / `clean_ack` 不改）。
7b. **v5f**：深挖问句以“吗”结尾不问（`no_yes_no`）；答过一次深挖后，下一问若只是请老人把刚答的再讲一遍（不问下文 / 谁 / 谁说了什么，又点到刚答里新冒出的东西）不问（`no_repeat_last`，`interview.repeats_last`）；两者都按“校验不过”处理（不深挖，按原收尾）。
8. **记录**：每题 `deepen.log` 记每次考虑的结果（问了 / 跳过及原因、上一句字数、本题字数、字面已有的维度、问句、校验错误），每条深挖发言带 `dimension`。
9. **开关**：配置里没有 `deepen` 块时代码路径与 v4d 完全相同（离线回放 sim-hv4d 0 差异，见 ITERATIONS）。

## 测试设计

- 同一批人、同一批题跑两遍：A = v4d（`--policy` 缺省），B = v5a（`--policy docs/prototypes/full-interview-v5/speaker-config.json`）。老人行为照旧按 sha256(人物|题|轮次) 固定抽样，A/B 遇到的是同一个“老人”；B 在深挖之前的每一步与 A 逐字相同，命中 A 的缓存。
- 计划（`plan_story.py`）：在 split.json 的迭代组 / 留出组里，资料多于 1000 字（资料按题检索）的人中，取至少 3 道故事题有素材的人（测试集对应到该题的摘录，其次是模拟器检索分 ≥4 的相关摘录），按资料量分层用固定种子抽取；每组另加一位资料很少、此前跑过同一窗口的人（迭代组林恆富，留出组李金蕾），A 侧基本命中缓存，也专门覆盖“深挖问到资料里没有的细节”这种情况。
  - 迭代组：陳信妹 WK01 WK05 WK06b；王成偉 SK01c GR01b WK05；孫樸生 CH03 RV06 RV13；李福英 CH05 WK05 RV02；林恆富 FM02 FM03 FM04 FM04b（FM04 为事实题）。
  - 留出组：楊秀峰 CH05 CH06b GR01b；李金蕾 FM02 FM03 FM04 FM04b。
- 规模：任务书建议约 8 人 × 3–4 题。按实测单价（判定约 2.2k token、说话层约 1.2k）估算，每道新题 A 约 4.5k、B 再加约 3k，8 人 × 3 题的 A+B 就要约 18 万，超过本阶段 15 万的上限，所以迭代组取 4 + 1 人、留出组取 1 + 1 人。
- 老人资料上限：每题约 1000 字（`persona.MATERIAL_CAP`）。深挖问到资料里没有的东西时，模拟老人按指令说记不清，这是真实情况；`story_metrics.py` 把它（`unknown_material`）与抽样到的“不想多说”（`unknown_sampled_reluctant` / `declined_sampled`）分开统计。

## 复现

```sh
export SHINIAN_RELAY_OUT=/mnt/user-data/outputs/relay/jobs SHINIAN_RELAY_IN=/mnt/user-data/uploads
P=docs/prototypes/full-interview-v5
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group iteration --name st5-a-it
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group iteration --policy $P/history/speaker-config.v5c.json --name st5-b5c-it
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group holdout --name st5-a-ho
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group holdout --policy $P/history/speaker-config.v5c1.json --name st5-b5c1-ho
python3 tools/interview_eval/simulate/story_metrics.py A=st5-a-it+st5-a-ho B=st5-b5c-it+st5-b5c1-ho
python3 tools/interview_eval/simulate/deepen_bench.py --from st5-b5c-it --name <名字> --policy <新配置>   # 只重发深挖调用的对照台（本阶段未用）
python3 tools/interview_eval/simulate/diff_runs.py sim-hv4d <v4d 离线回放>        # 开关关闭逐项相同
# 第六阶段
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group iteration --policy $P/history/speaker-config.v5e.json --name st6-b5e2-it
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group holdout --policy $P/speaker-config.json --name st6-b5e1-ho
python3 tools/interview_eval/simulate/story_metrics.py A=st5-a-it+st5-a-ho v5d=st6-b5d-it B=st6-b5e2-it+st6-b5e1-ho
python3 tools/interview_eval/simulate/style.py st5-a-it+st5-a-ho st6-b5e2-it+st6-b5e1-ho
python3 tools/interview_eval/simulate/material.py st5-a-it+st5-a-ho st6-b5d-it st6-b5e2-it+st6-b5e1-ho --offline
python3 tools/interview_eval/simulate/scope_impact.py
# 第七阶段
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --plan $P/story-plan.json --group iteration --policy $P/speaker-config.json --name st7-b5f-it
python3 tools/interview_eval/simulate/story_metrics.py A=st5-a-it v5e=st6-b5e2-it v5f=st7-b5f-it
python3 tools/interview_eval/simulate/style.py A=st5-a-it v5e=st6-b5e2-it v5f=st7-b5f-it
python3 tools/interview_eval/simulate/material.py A=st5-a-it v5e=st6-b5e2-it v5f=st7-b5f-it --offline
```
