# 判定层 v3j + 说话层 v4d 运行合同

由 `scripts/build_interview_v3j_runtime.py` 生成，不要手改。除 `provider-settings.json`、本文件和 `manifest.json` 外，
每个文件都与离线已测原件逐字节相同：判定层取自 `docs/prototypes/full-interview-v3j/`，说话层提示与配置取自
`docs/prototypes/full-interview-v4/`（v4d），OpenCC 来源记录与现网运行合同相同。题库为冻结的 83 题 v2。

`manifest.json` 列出全部文件的 SHA-256；部署时用 `INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256` 固定 manifest 本身的
SHA-256，目录里出现未列出的文件、任一文件不符或模型参数开启 thinking 时拒绝启用。
