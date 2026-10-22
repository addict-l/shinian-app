# 采访链路优化（分支 `interview/question-optimization`）

2026-10-22 起，采访优化的每个**可提交版本**都推送到 GitHub 分支 `interview/question-optimization`，由用户审阅后合并到 `main`。
本分支只新增离线候选与评测工具，**不改** `ios/`、`android/`、`cloud-deployment/`，也不改线上运行合同；合并到 `main` 不会改变 App 或阿里云后端的行为。接入后端是单独的提交块，按[开发约定](../../../AGENTS.md)另行验证、审核和发布。

## 版本台账

| 版本 | 层 | 结果 | 状态 | 位置 |
| --- | --- | --- | --- | --- |
| 现网 v2 | 抽取 → 复核 → 至多一次修复 | full45 关键点约 70% | 线上（`cloud-deployment/backend/app/ai/interview_runtime`） | `docs/prototypes/full-interview-v2/single-question-v2/` |
| **v3j** | 判定层：每个检查点一次判定调用，代码拼装与引擎校验 | full45 197/204 = **96.6%**；随机 10 人门槛缓存 42/43、关缓存真实调用 43/43 | 离线候选，已测 | `docs/prototypes/full-interview-v3j/` + `tools/interview_eval/pipelines/v3j.py` |
| **v4d** | 说话层：只改怎么说（承接、追问、收尾转题），不改问什么 | 模拟访谈迭代组 8 人 × 4 题：自然 3.97、贴合 4.03、时机 4.69、语气 4.72，硬性违规 2.8%（现网固定话术 2.47 / 2.21 / 2.93 / 3.21，违规 44%） | 离线候选，已测 | `docs/prototypes/full-interview-v4/` + `tools/interview_eval/simulate/` |
| v4e | 说话层：追问恢复“把老人刚讲的事放进问句”，转题不套模板 | 未测完 | 开发中，提示存于 `history/speaker-prompt.v4e-untested.txt` | 同上 |

固定条件：模型 DeepSeek `deepseek-v4-pro`，**thinking disabled**；题库为冻结的 83 题 v2（[冻结清单](../../question-bank-freeze-v2.json)，不得修改）；模拟老人和量表打分由 Claude Haiku 担任，不用 DeepSeek。

## 合并说明（给合并的人／工具）

- 分支从 `main` 的 `ac9fd10` 拉出，只新增文件，外加本目录和 [第二阶段导航](../README.md) 的一行链接；与 `main` 上其他工作没有重叠路径，正常应可快进或无冲突合并。
- 若 `main` 也改了 `docs/phase-2/README.md`，冲突只在表格最后一行附近：两边的行都保留即可。
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
