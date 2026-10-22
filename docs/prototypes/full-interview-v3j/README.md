# 判定层 v3j（离线候选）

2026-10-22。在 `single-question-v2` 运行合同之上重做“这一段回答答到了哪些要素、下一步追问哪个”。未接入后端。

## 链路

1. 每个检查点一次判定调用（`judge-prompt.txt`，deepseek-v4-pro，thinking disabled）：对每个目标输出 best/about/kind/concept/match/units/core/subject。
2. 状态在代码里推出；值、证据、主体、阶段、关联由代码确定性拼装（`tools/interview_eval/pipelines/v3j.py`）。
3. 只有出现否认时才发一次核对调用（`verify-prompt.txt`），且只允许把 known 改为 none。
4. `engine.js` 校验并做追问决策，含按 `semantic-roles.json` 的同类目标保护。

`contracts.json`、`engine.js` 等与 v2 同源，仅补了 semantic_role 与引擎修正；题库仍是冻结的 83 题。

## 结果

- full45（45 位开发人物、204 个关键点）：197/204 = 96.6%。
- 随机 10 人门槛：缓存回放 42/43，关缓存真实调用 43/43。
- 复现：见 [评测工具说明](../../../tools/interview_eval/README.md)；迭代过程见 [v3 迭代记录](../full-interview-v3/ITERATIONS.md)。

`../full-interview-v3/` 是 v3d–v3i 的开发历史运行时与提示，供 `pipelines/v3_judge.py`、`v3g.py`、`v3h.py` 回放用，不是候选。
