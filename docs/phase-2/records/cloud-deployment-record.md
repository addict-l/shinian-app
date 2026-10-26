# 第二次大提交：部署记录

本文件记录 B01/B02 的模型切换，B03 的兼容部署见[该块验收材料](../b03/phase-2-b03-verification.md)。童年采访验证使用独立候选环境，状态见[试点入口](../childhood-pilot/README.md)。一期部署快照见[历史记录](../../phase-1/records/cloud-deployment-record.md)。

## B01/B02 DeepSeek Flash 部署（2026-10-13）

用户明确要求将 DeepSeek API 写入真实云端配置并继续 B02；部署前在 `/opt/shinian-backups/pre-deepseek-b02-20261013/` 保存了生产环境文件、旧 API 镜像、后端源码、MySQL dump、媒体文件及 Nginx/TLS 归档。备份文件均为服务器本地 0600 权限，SHA256 校验通过；DeepSeek 凭据仅存于生产环境文件，暂存文件在激活后删除。

候选后端源码包 SHA256：`3858e3beeba7cb69a1336848a76d7f667d7f4856342a550d4f716cea6d5e1c4c`；正式镜像：`sha256:5d02956a447fb7b51e688cffddf9ca38833aed24805c34960f912261967fc991`。运行迁移保持 `f10100000001`。生产配置现用 `https://api.deepseek.com` / `deepseek-flash`，访谈主/备模型与草稿模型均用 DeepSeek；并行访谈已启用 `LLM_TURN_PARALLEL=true`、`LLM_TURN_STRATEGY=parallel_tasks`。配置更新和 API 重启均由用户指示执行。

隔离随机数据库 273 项回归通过并在结束时清理；21 个合成 DeepSeek HTTP 场景全部通过，短请求上限 6 秒、长篇回应/草稿上限 10 秒，实测最慢分别为 2.283 秒和 2.114 秒。37 次候选模型调用均成功，合计 116,939 输入与 2,366 输出 tokens。线上健康检查、直接结构化 JSON API 冒烟及公网未认证 401 边界通过；正式迁移与只读健康检查未创建或修改人物、消息、回忆及照片。独立激活配置备份位于 `/opt/shinian-backups/deepseek-config-20261013-020414/`，并行策略回退备份位于 `/opt/shinian-backups/deepseek-parallel-20261013-020551/`。

用户随后完成 B01/B02 合并检查并授权正式 commit，要求标注换模为 DeepSeek Flash（ds flash）。本次归档主工程、云端后端及独立验证目录，精确提交映射保存在独立验证目录 `artifacts/phase-2-b02/final-revisions.json`，不重新部署相同业务代码。前端、真机语音与真实家庭认证后的业务流程未在本次验证；隔离故事仅为合成内容。


## C01–C03 采访整合发布（2026-10-23）

本轮按用户条件授权接收 Claude ece64ea、整合 main 246a2c4 后发布 `ed38ab2c4738874d01b4470a10a8826c1c3da90d`；实际镜像 `sha256:b33819f706e40bf46b23fcce5f3a88252d4cb0c9904698417232e99c60332fac`。pipeline 仍为 v3j_v4d，runtime pin 不变，保留完整 OSS/认证/媒体配置，切换前后全表及媒体指纹一致，备份校验通过，v2-only 兼容回退已准备。候选 MySQL HTTPS 15 场景/89 检查和发布后正式 HTTPS 独立测试家庭 9 场景/59 检查通过；未合并 main，正式三连轮质量门槛仍待办。固定版本、工具问题、真实原话、证据哈希与下一轮事项见 [C01–C03 回执](../interview-optimization/handoffs/2026-10-23-c01-c03-cloud-release.md)。

## 采访入口会话排序修复（2026-10-23）

用户明确批准“发布修复并恢复采访”后，将 `a1ecee61eae633898f1ba3a7200a630ca66a32c2` 发布到真实阿里云，同时推送 main 和共享分支。镜像 `sha256:d7b94334ac909feb59775a19b5b27fde48737153ff919bdf83eb2192f809b0d8`，release `/opt/shinian-releases/session-list-sort-a1ecee6-20261023`。仅修复会话列表完整 JSON 行排序导致的 MySQL 1038/采访入口 503；采访流程、模型、runtime pin 和 OSS 不变。

本地/云端 Ran 80、skip 1、失败/错误 0；独立 MySQL/HTTPS 验证及原受影响家庭只读验证通过。备份校验与切换窗口全表/媒体指纹一致，v2-only fallback 已准备、未触发。发布后正式 HTTPS 业务列表 200、匿名认证 401；现有模拟器此前失败人物的 conversation POST/GET 200，显示人生骨架第一题，可继续用户测试。未改键盘设置，未代答或保存回忆。具体证据、工具和 Claude 下一轮继承要求见[最新修复回执](../interview-optimization/handoffs/2026-10-23-session-list-sort.md)。此前 C01–C03 后来已获授权合入 main；上述历史记录的“未合并”仅为当时发布状态。


## 采访 V6 冻结与真实云端发布（2026-10-27）

用户明确批准V6冻结、真实阿里云发布及main/共享分支同步。产品8799b52，镜像1d84622e…902e68ae，pipeline v3j_v5f，listening pin1062b6c2…a76487；旧v4d pin和所有状态兼容保留。受控release `/opt/shinian-releases/interview-v6-8799b52-20261027`，当前production override与只切v4d的fallback均在其中。备份可读性/哈希、切换窗口全表及媒体指纹一致，OSS/挂载/端口/其他env保持。

最终镜像Ran130/skip1，正式HTTPS独立合成家庭最终14场景/154检查通过；初次并发入口死锁503另保留，同请求重试恢复，并发根因未修复。192个成功采访调用模型/参数/请求摘要一致、thinking disabled。原始记录、工具、冻结版本、同步边界和下一轮责任见[V6回执](../interview-optimization/handoffs/2026-10-27-v6-release.md)。质量三连轮门槛仍未宣称通过，未改客户端代码或键盘设置。
