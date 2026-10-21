# 童年三层采访试点

这是第二阶段中独立进行的后端候选试点：固定六个童年采访主线，事件 AI、回答 AI、模块 AI 分工，由代码控制器选择局部问题和推进。当前仍待人工审查，正式家庭服务及 App 默认聊天尚未启用。

| 内容 | 文件 |
| --- | --- |
| 实施边界 | [接入计划](childhood-backend-pilot-plan.md) |
| 单组结果与恢复验证 | [后端验收材料](childhood-backend-verification.md) |
| 四组连贯性问题 | [多组测试报告](childhood-multi-test-report.md) |
| 三层实际 Prompt 与合并稿 | [Prompt 入口](prompts/README.md)、[统一 Prompt](prompts/04-unified-guided-childhood.txt) |
| 单组可读问答与草稿 | [问答](examples/childhood-backend-dialogue.md)、[草稿](examples/childhood-backend-drafts.md) |
| 四种回答风格 | [M01 完整回答](examples/childhood-multi-M01-dialogue.md)、[M02 零碎回答](examples/childhood-multi-M02-dialogue.md)、[M03 未知与拒绝](examples/childhood-multi-M03-dialogue.md)、[M04 补充与更正](examples/childhood-multi-M04-dialogue.md) |
| 四组生成结果 | [草稿对照](examples/childhood-multi-drafts.md) |

完整 HTTP 问答与逐项状态已移入 `shinian-validation/artifacts/archive/phase-2/childhood-pilot/raw-documents/`，详见[本地产物规则](../../project/local-artifacts.md)。测试报告中的失败、误判和未覆盖范围继续保留，不因文件归档而变成通过。
