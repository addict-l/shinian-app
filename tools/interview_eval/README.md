# 采访链路评测工具

离线评测采访链路的两件事：判定层的关键点准确率（`run.py`），以及接近真实使用的模拟访谈（`simulate/`）。不影响 App 与后端。

## 准备

- 测试集（55 人，不在 Git 里）解压到 `.runtime/interview-eval/testset/`，或设 `SHINIAN_TESTSET_DIR`。
- 工作数据默认都在 Git 忽略的 `.runtime/interview-eval/`：`cache/`（DeepSeek 回复按内容哈希缓存）、`runs/`（每次运行结果）、`cache-haiku/`、`relay/`。可用 `SHINIAN_EVAL_HOME` 或 `SHINIAN_EVAL_CACHE`、`SHINIAN_EVAL_RUNS` 等单独改。
- 需要 Python 3 与 Node.js（`engine_bridge.js` 常驻调用运行合同的 `engine.js`）。

## DeepSeek 调用

调用在自己电脑上执行，密钥不离开本机：把 `relay/` 复制到本机目录（如 `D:\shinian_evl`），运行 `import_key.py` 导入 key，双击 `start_relay.bat`。
评测端把每批调用写成 `relay/jobs/*.request.json`，本机中转写回 `*.response.jsonl` 与 `*.done.json`；两端之间的搬运见 `shuttle.py`，补缓存用 `ingest.py`。
相同的 system/user/参数自动命中缓存；只改代码时用 `--offline` 回放，0 token。`--fresh` 跳过缓存做真实重跑。
不经中转的直连模式（云端运行用）：`SHINIAN_DS_MODE=direct`，密钥只从环境变量 `DEEPSEEK_API_KEY` 读（不落盘），`DEEPSEEK_BASE_URL`、`SHINIAN_DS_CONCURRENCY`、`SHINIAN_DS_TIMEOUT`、`SHINIAN_DS_MAX_CALLS` 可配；请求体由同一个 `relay/ds_relay.py` 的 `one_call` 生成，缓存与中转模式完全通用，任何调用失败即停（`SHINIAN_DS_STRICT=0` 关闭）。

## 判定层（关键点）

```sh
python3 tools/interview_eval/run.py --pipeline tools/interview_eval/pipelines/v3j.py \
  --dataset .runtime/interview-eval/runs/datasets/full45.json --name f45-check --offline
python3 tools/interview_eval/run.py --pipeline tools/interview_eval/pipelines/v3j.py --people 10 --name gate-01   # 随机 5–10 人门槛
python3 tools/interview_eval/explain.py .runtime/interview-eval/runs/f45-check   # 失败详情
```

打分沿用冻结的 `tools/run_full_interview_eval.py` 与金标准 `docs/prototypes/full-interview-evaluation/single-question-v2-gold.json`。改判定层后，离线回放 full45 须仍 ≥194/204。
`pipelines/`：`v2_baseline.py`（现网流程）、`v3j.py`（当前候选），其余为开发历史。
后端接入的一致性回放读同一缓存、0 token：`cloud-deployment/backend/tests/test_interview_v3j_full45_replay.py`（full45 须 197/204 且逐检查点同 `branch-check-v3j`）、`test_interview_v4d_sim_replay.py`（sim-hv4d 说话层输入逐字相同）。改 `v3j.py` 或 v4 提示后，后端副本（`app/ai/contract_interview_v3j.py`、`interview_speaker.py`、`interview_runtime_v3j_v4d/`）要同步，并重跑这两项。
改老人信号、收尾规则或补充阶段的“没有补充了”识别（`interview_speaker.py` 的 `elder_signal` / `decide` / `supplement_end`，模拟器 `simulate/interview.py` 的同名规则须逐字相同）后，用 `control_impact.py` 对所有已存老人回答（`sim-*` 会话、full45、可选 `--cloud` 云端原始记录目录）列出新旧读法的每一处变化，0 token：`python3 tools/interview_eval/control_impact.py --base <旧提交> --cloud <原始记录目录>`。

## 模拟真实访谈（说话层）

```sh
python3 tools/interview_eval/simulate/run_sim.py --mode v4 --group iteration_run --name sim-xxx      # 改后
python3 tools/interview_eval/simulate/run_sim.py --mode baseline --group iteration_run --name sim-b   # 现网固定话术
python3 tools/interview_eval/simulate/fu_bench.py --group iteration --name fu-xxx --from f45-check   # 追问对照台（取 v3j full45 运行里的追问点）
python3 tools/interview_eval/simulate/export_html.py --out 对照.html --title ... --run "改后=sim-xxx" --run "改前=sim-b"
```

模拟老人与打分走文件队列（`<runs>/persona-queue`、`<runs>/scorer-queue`），由 Claude Haiku worker 按 `simulate/WORKER.md` 处理；DeepSeek 只负责采访一侧。
完整采访（生产 V6 流程）：`simulate/run_full.py`（`--persona queue|openai`，老人后端见 `simulate/persona_backend.py`；DeepSeek 不扮演老人），0 token 自检 `simulate/v6_replay.py cache <运行>`（部分完成的运行也可，封网回放、已完成题须逐项相同）。
老人行为按 `sha256(人物|题|轮次)` 固定抽样，与被测版本无关，改前改后遇到的是同一个“老人”。`tokens.py`、`simulate/stage_tokens.py` 记账。

## 故事题深挖（v5，模拟器原型）

`docs/prototypes/full-interview-v5/`：故事题标签、深挖提示与配置、会话计划与迭代记录。`run_sim.py --plan <计划文件> --group <组>` 用计划文件代替 split.json；`--policy` 指向带 `deepen` 块的配置即开启深挖，没有该块时与 v4d 逐项相同。
`story_metrics.py`（故事题字数、深挖次数与原因、维度、老人对深挖的回答、量表，`RUN1+RUN2` 可合并）、`diff_runs.py`（两次运行除耗时与缓存标记外是否逐项相同）、`plan_story.py`（生成故事题计划）、`deepen_bench.py`（只重发深挖调用的对照台）；`export_html.py` 会标出深挖问句。
