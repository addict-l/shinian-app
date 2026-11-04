NEED_RELAY 120 st8 第1轮：st8-b61-it 续跑（--resume）+ 骨架 11 题 V6.1/V6.2 对照 st8-b61-sk / st8-b62-sk（黄小荣，判定多数走缓存）+ V6.2 迭代组 st8-b62-it（家庭生活 6 题×2 人），四个运行器同时跑，采访调用 thinking disabled，预计约 120 次 DeepSeek、约 20 万 token；作业名 st8-b61-it-p0xx / st8-b6?-sk-p### / st8-b62-it-p###
NEED_WORKERS 2 队列 persona + scorer（cd /home/claude/v62-wt && SHINIAN_EVAL_HOME=/home/claude/addict-l/shinian-app/.runtime/interview-eval python3 tools/interview_eval/simulate/queue_worker.py next all 90；说明 tools/interview_eval/simulate/WORKER.md）st8 第1轮模拟老人约 100 次，之后量表打分约 40 次、回忆录素材打分约 20 次

# 采访 V6.2 迭代记录（BRIEF12，2026-11-03）

工作树 /home/claude/v62-wt，分支 interview/claude-v62（基于 origin/interview/question-optimization 4414926 = V6.1 代码 d7e28b4 + 回执；origin/main 4f9c40d 已包含）。记账前缀 st8-。

## 0. 已用 token（stage_tokens.py，开工时）
- 采访侧（BRIEF5 起，100 万上限账户）：st5- 133,110 + st6- 150,538 + st7- 63,842 = 347,490；st8- 0。
- 更早采访阶段（不在该账户）：sim- 1,113,522、rp4- 356,293、full45/hard66/focus60 等。成书 mb1-/mb2-/mb3-（不计采访）。

## 1. 开工时的关键发现（0 token）
- 模拟老人素材选择（persona.material）对黄小荣 N-6733a23cd1：72 道模块题里 69 道只拿到开头一段 E001（借田种稻那段，词面打分全低于阈值走兜底）；工作+家庭 24 题全部只有 E001。完整 84 题里“同一故事换说法重讲”主要是模拟器造成的。
- mb2-full84-long 老人原话按“前一句采访者话”分类（4-gram 覆盖≥0.5 计重讲）：入口首答 9,238 字新 46%；追问 1,350 字新 40%；深挖 598 字新 33%；草稿入口“您还有什么想补充的吗”3,988 字新 22%；补充 1,731 字新 19%。首答只看到固定入口题，重讲全部来自模拟器/题库；草稿与补充环节是采访流程里重讲最多的地方。
- 深挖选点反复问已讲过的借田种稻（SK01c/CH01/CH05/CH06b/GR01b），放大了重讲。

## 2. 范围与分组（预算 ≤40 万，先定后跑）
- 每题新发约 9–10k token（判定 2.3k×2.3 次 + 说话层 + 深挖），4–6 人×2 个完整模块链（≈100 题/轮）远超预算，按预算缩为：
- 模块链：家庭生活 FM01–FM04b（6 题，4 道故事题含敏感 FM03、2 道事实题），按生产每个模块一条状态链。
- 迭代组（调）：余华 N-756a382469、李福英 N-63f4aa2206（迭代分组里素材按题变化最多的两人）。
- 留出组（只看不调）：易芳運 N-568db56d4d（留出分组）、黄小荣 N-6733a23cd1 健谈变体（sim-config-long；前面模块按 mb2-full84-long 的已讲内容作为跨题记忆种子，即重讲现象的原样本）。
- 迭代轮次用基线对话上的单步对照（深挖/收尾调用），定版后迭代组+留出组各跑一次完整流程。
- 敏感性检查（只用 Haiku）：同一人物“素材充足”设定（每题按相关度给满素材）下的首答跨题重讲率。
