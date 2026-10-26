# 判定层 v3j + 说话层 v5f（故事题深挖）运行合同

由 `scripts/build_interview_v3j_runtime.py --bundle v5f` 生成，不要手改。判定层文件与 `interview_runtime_v3j_v4d` 逐字节相同
（取自 `docs/prototypes/full-interview-v3j/`）；说话层提示与配置、深挖提示和 23 道故事题标签取自
`docs/prototypes/full-interview-v5/`（v5f，与模拟器测过的原件逐字节相同）。除 `provider-settings.json`、本文件和
`manifest.json` 外不改任何文件。题库为冻结的 83 题 v2；`story-questions.json` 的题号、题序和入口问题在启动时与题库核对。

部署时用 `INTERVIEW_PIPELINE=v3j_v5f`、`INTERVIEW_V5F_RUNTIME_DIR` 和 `INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256` 启用；
目录里出现未列出的文件、任一文件不符、题标签与题库不符或模型参数开启 thinking 时拒绝启用。
