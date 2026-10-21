# 第二次大提交：验证记录

本文件收录 B01/B02 联合验收；[B03](../b03/phase-2-b03-verification.md)、[B04](../b04/phase-2-b04-verification.md)和[童年试点](../childhood-pilot/README.md)分别保存各自材料。一期历史见[第一阶段](../../phase-1/records/validation-record.md)。

## B01/B02 联合验收与 DeepSeek 切换（2026-10-13）

B01/B02 按用户指示连续实现后一次提供检查材料，中间不做单独人工审核或 commit。B01 本地及云端隔离回归各 222 项通过，原 iPhone 17 Pro 的完整回复计时为 5.239 秒；合成云端短回复重测为 2.767–4.876 秒，长篇回应 3.105 秒。B02 最终候选通过 273 项云端隔离回归；新增兜底的 3 个本地定向用例通过。

切换后的 DeepSeek 候选用 21 个合成 HTTP 场景覆盖连续讲述、短回答、未知时间、暂停、同一事件延伸、另一独立事件、返回旧事、代述称呼及长稿。全部请求/草稿通过，短回复最慢 2.283 秒，长篇讲述应答 1.099 秒，长草稿 2.114 秒；37 次模型请求均成功，总计 116,939 输入及 2,366 输出 tokens。某次较早候选曾出现边界与称呼校验 502，日志定位为模型回复偶发违反访谈策略，而非上传体积或接口连接错误；在并行回复有限修复后加入经同一策略校验的短兜底，最终 21 场景复测全通过。真实线上容器另以不写入家庭数据库的结构化 JSON 请求验证配置有效。

候选源码与日志在独立验证目录 `/Users/student03/Desktop/shinian-validation/artifacts/phase-2-b02/`，包括 `deepseek-cloud-final.log`、`deepseek-cloud-tests.log`、`deepseek-http-final.jsonl` 与 `deepseek-model-calls.jsonl`；原始云端日志保存在发布目录的 `logs/`。B01 原始失败与模拟器截图保持在该验证目录的 B01 归档中。最终已部署镜像与备份身份见 [云端部署记录](cloud-deployment-record.md#b01b02-deepseek-flash-部署2026-10-13)。用户已阅读问答整理文档并明确批准 B01/B02 正式提交，要求标注切换 DeepSeek Flash（ds flash）；最终三处提交身份记录于独立验证目录 `artifacts/phase-2-b02/final-revisions.json`。
