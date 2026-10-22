# 说话层 v4（离线候选）与模拟真实访谈

2026-10-22。判定层（v3j）决定问什么；说话层只决定怎么说：承接老人刚说的话、把追问落到老人当前讲的事上、自然地收尾或转到下一题。未接入后端。

## 文件

| 文件 | 作用 |
| --- | --- |
| `speaker-prompt.txt` | 说话层提示，**当前为 v4d（最新已测）** |
| `speaker-config.json` | 说话层模型参数与收尾规则（追问上限、同目标上限、老人说“记不清/不想讲/累了”即收） |
| `history/` | v4a–v4d 各版提示；`speaker-prompt.v4e-untested.txt` 为开发中的 v4e |
| `simulator-prompt.txt`、`sim-config.json` | 模拟老人：只讲测试集里该人物的真实资料，按固定种子抽样出短答、跑题、不想多说、想歇、语音错字 |
| `scorer-prompt.txt` | 量表盲评：自然、贴合当前事件、时机、单一不预设、语气，及硬性违规 |
| `split.json` | 45 位开发人物分为迭代组 30 人、留出组 15 人（固定种子） |
| `ITERATIONS.md` | 迭代记录（HB1 基线 → v4a–v4e） |

## v4d 结果（迭代组 8 人 × 连续 4 题）

| 指标 | v4d | 现网固定话术 |
| --- | --- | --- |
| 自然不生硬 | 3.97 | 2.47 |
| 贴合当前事件 | 4.03 | 2.21 |
| 时机（结束自然） | 4.69 | 2.93 |
| 语气 | 4.72 | 3.21 |
| 硬性违规率 | 2.8% | 44% |

现网固定话术的追问 100% 照念合同问句；v4d 为 0。单独的追问对照台（49 个追问点）上 v4d 贴合 3.65，低于 v4c 的 3.94，v4e 针对此项，尚未测完。

v4e 的一处流程改动（老人歇会儿后点“继续”，接下一题那句改由说话层写）由 `speaker-config.json` 的 `rest_resume_by_speaker` 控制，v4d 为 false。
用本目录当前文件离线回放 `run_sim.py --mode v4 --group iteration_run --offline`，71 次 DeepSeek 调用与 67 次 Haiku 回答全部命中缓存，结果与 v4d 原运行逐项一致。
跑 v4e：`--speaker-prompt docs/prototypes/full-interview-v4/history/speaker-prompt.v4e-untested.txt --policy docs/prototypes/full-interview-v4/history/speaker-config.v4e-untested.json`。
