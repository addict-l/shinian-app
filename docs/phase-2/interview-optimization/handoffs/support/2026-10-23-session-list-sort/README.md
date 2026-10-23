# 会话大 JSON 排序修复：可复核工具与结果

产品修复固定为 `a1ecee61eae633898f1ba3a7200a630ca66a32c2`，具体结论见[回传单](../../2026-10-23-session-list-sort.md)。本目录是工程验证证据，不是一轮新的采访质量评测。

- `prepare_sort_candidate.py`、`activate_sort_release.py`、`verify_sort_candidate.py` 为本轮实际执行源码，保留原路径和一次性 release 名称；不得直接重跑已完成的生产切换。
- `verify_sort_production.py` 是原执行脚本的脱敏副本：将真实家庭 UUID 改为必填环境变量 `SHINIAN_PROBE_FAMILY_ID`；副本未执行，原执行源码哈希列于 `verification-summary.json`。不会随仓库提供真实家庭身份、认证文件或业务原文。
- 两份 HTTPS 验证器依赖上一轮的 `../2026-10-23-c01-c03/verify_candidate_https.py`，实际运行时动态导入本机 artifacts 同名文件。迁移机器时将该引用及 A/P 路径改为自己的受控位置；已有独立测试家庭的认证只从本机 private 读取。不要将令牌复制进命令、日志或仓库。
- 候选工具固定 SSH 密钥引用和服务器地址，要求已有授权；候选数据库独立、TLS 为独立 loopback Nginx+有效正式证书，SSH 本地端口 28446 转发到 18446。发布完成后该候选服务、Nginx 和本轮转发均停止，库与证据保留。
- 发布脚本在服务器导入 `/home/admin/prepare_sort_candidate.py`；完整受保护环境、OSS 挂载与 v2-only fallback 位于 release，本目录只有非秘密摘要。
- `source-manifest.json` 是固定 Git 源码哈希；`data-before/after.json` 只含全部业务表和媒体的数量/指纹，无业务原文；`backup-verification.json` 只含服务器受保护备份的尺寸/哈希，不提供备份内容。

最小产品回归：在固定 SHA 的 `cloud-deployment/backend` 运行：

```sh
python3 -m unittest tests.test_contract_interview_workflow.WorkflowTests.test_session_list_orders_large_histories_without_sorting_json -v
python3 scripts/build_interview_v3j_runtime.py --check
SHINIAN_EVAL_HOME=/受控位置/interview-eval python3 -m unittest discover -s tests -p 'test_*.py' -v
```

依赖按后端 requirements 安装；完整回放资料仍为用户提供的 `claude-interview-replay-data-20261023.zip`，SHA-256 `f8b39141903954ad7d52415b9e84f724e57bb93a841a1493e6d3828749b3f8b7`。没有该私有资料时明确标为无法重现回放，不能将 skip 算通过；holdout 未调参。实际本地/云端均 Ran 80、skip 1、失败/错误 0，full45 为原缓存 197/204、0 miss。

单测日志、原始1038 red记录、发布日志及本目录文件另交用户 ZIP；日志 SHA 在 summary。附件未声称 Claude 云端已经接收。本目录 JSON 足以通过 Git 取得候选、发布状态、指纹和接口结论；真实数据库与秘密不可由该附件重建。
