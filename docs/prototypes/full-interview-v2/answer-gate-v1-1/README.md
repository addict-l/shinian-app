# 采访答案门原型 v1.1

本地、离线业务评估原型。对同一组公开真实访谈回放，比较冻结的单问句 v2 链路与“定位候选原话 → 独立判定当前目标 → 程序组装既有引擎提案”的链路。原始题库、合同、Gold、评分器、DeepSeek Pro、关闭思考模式及最多一次内部修复均保持不变。原型不会部署到应用或线上服务。

运行时先从 `run-single-question-v2-round001` 的冻结 runtime 与 dataset 各准备一个全新会话，再用标准 `tools/run_full_interview_eval.py` 跑对照组、用本目录的 `run.py` 跑原型组。两组采用同一真实材料；原型仍使用原引擎 `analyze` 与原评分器 `score_session`。原型提示、代码及运行设置在开始调用前记录 SHA256，不会覆盖原有回归。

`locator-prompt.txt` 只返回候选原话编号。`judge-prompt.txt` 独立核对语义并返回紧凑状态；`run.py` 只复制原话、组装既有引擎所需结构，不能创造事实。技术调用错误和受访者未回答分别记录。

这组材料是开发中已见过的公开访谈回放，不能证明老人对新问法的实时交互已经通过正式验收。通过率、重复追问及响应时间须一起报告；并发整批墙钟时间与单检查点模型 HTTP 时间分别列示。

v1.1 仅修复 v1 原型的确定性组装错误：判定器返回 `links`、`precision`、`stance` 等空值时，组装器不再把这些空值发送给原引擎。v1 的整批原始调用和评分保留，不覆盖。

试验记录：v1 首轮完整批次为 28/33，重复或不必要追问 1 次、协议无效 1 次；v1.1 修复空值组装后另起独立完整批次，结果为 29/33、重复或不必要追问 1 次、协议无效 0 次。两轮均使用开发中已见过的同一批材料；不能把两轮差异全归因于修复，模型输出也会有波动。

## 复现

在项目根目录运行；`--out` 需使用尚不存在的目录。两组必须使用同一个冻结来源，不能重抽或修改标注。现有运行器通过已配置的隔离评估容器调用 DS；不要把测试指向生产 API。

```sh
python3 tools/run_full_interview_eval.py prepare --runtime docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/runtime --dataset docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/dataset.json --out /tmp/answer-gate-control
python3 tools/run_full_interview_eval.py prepare --runtime docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/runtime --dataset docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/dataset.json --out /tmp/answer-gate-candidate
python3 tools/run_full_interview_eval.py run --session /tmp/answer-gate-control --split all --concurrency 4
python3 docs/prototypes/full-interview-v2/answer-gate-v1-1/run.py /tmp/answer-gate-candidate --concurrency 4
python3 docs/prototypes/full-interview-v2/answer-gate-v1-1/compare.py /tmp/answer-gate-control /tmp/answer-gate-candidate --out /tmp/answer-gate-comparison.json
```

比较脚本强检数据、合同、模型配置和每次真实调用的关闭思考设置。严格通过率、重复或不必要追问及单检查点模型 HTTP 时间为主指标；同时列出误收、漏提、协议失败、调用数与并发批次墙钟时间。原评估器的 `first_code_decision` 不适用于本原型，因为第一模型调用只定位候选，使用最终检查点分数和配对报告。
