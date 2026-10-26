# v5f 候选验证工具与最小复现

对应回执：[2026-10-27](../../2026-10-27-20013ab-cloud-validation.md)。候选代码 `20013ab6339b4f2c34205b3bcda5318bb4234631`，测试检出 `9915707504d3edc8e813961c0e958b14ea068313`。**候选未通过，未发布生产。** 本目录是验证工具和最小合成复现，没有生产配置、凭据或真实家庭原文。

## 本地复现 S01

在候选后端依赖环境中执行：

```sh
python3 reproduce_wk01.py --backend /absolute/candidate/cloud-deployment/backend
```

使用已存的真实模型判定回复，不联网；真实 Node 引擎在 v4d/v5f 都把 `WK01-E2` 丢成 `missing`，出现 `repetition_is_not_explanation`。脚本退出 0 表示复现了缺陷，不能算验收通过。材料是合成验收文本，不是 gold 或留出样本。

## 工具范围

| 工具 | 用途与边界 |
| --- | --- |
| `prepare_story_candidate.py` | 固定 SHA 归档校验、两运行包 pin、原生产 265 文件校验、独立 MySQL/媒体、私有 HTTPS、候选与 fallback 配置；只准备、不切生产。运行目录已存在会拒绝重建。秘密留在云端 root 目录 |
| `cloud_fixture.py` | 只允许 `shinian_story_v5f_20261026` 数据库，核对合成测试家庭和会话后设置目标题；不提供模型回复。完整骨架从真实 API 起步，不使用该捷径 |
| `http_base.py` / `verify_story_https.py` | TLS 证书验证、真实 API、幂等请求日志、原样回答、场景验收与骨架续跑。脚本使用固定合成受访回答，不能当作真人或实时 AI 老人的质量测试 |
| `fault_proxy.py` / `run_fault_validation.py` | 仅对自己的候选注入一次 deepen 503；判定/说话仍去真实供应商；不记录请求文本或凭据；finally 恢复候选完整 env、镜像、挂载。生产不参与 |
| `collect_public_evidence.py` | 只读核查生产未切换与当前 pending 数量；白名单导出合成记录。SQL JSON `null` 按空值处理 |
| `export_and_audit.py` | 校验留存调用的参数/请求摘要/模型 ID，并检查审计完整性；HTML/TXT/JSON 原文一致性。回退调用丢失会单独报审计缺口 |
| `decode_client.swift` | 使用现有 iOS `LifeOverview`、`GuidedInterviewProgress` 解码真实响应，范围止于数据解码 |

这些是本轮固定路径的一次性工具，先阅读源码和回执，不要把准备脚本当通用生产部署器。它们没有生产切换动作。完整原文、缓存回放附件、状态和模型记录另交用户附件，包名与 SHA-256 见回执。

本轮准备归档漏带 `docs/question-bank-freeze-v2.json`，导致首次云端全量测试额外跳过 1 项。最终把固定 SHA 的该文件加入独立 `validation-complete` 测试树后重跑：Ran 98 / skip 1 / 失败错误 0；没有改后端镜像。初次只读嵌套挂载失败记录和测试工具的早期中断均保留在附件，不覆盖成成功。

## 继续候选测试

云端候选容器与私有 Nginx 在交付后暂停，数据库和证据保留。受控主机上恢复时，先检查生产状态和该目录现状，再启动同名候选容器及它自己的 Nginx；不修改生产 Nginx。SSH 的私钥仅是本机配置引用，不在附件。重跑需新场景名/独立测试家庭，避免把操作日志复用当新模型调用。

两份回放资料按交接单合并到 `SHINIAN_EVAL_HOME`；同名缓存必须内容相同，留出文件不用于调参。使用真实 Node、SQLite 和 `--network none` 的云端测试容器验证源树；实际问答另走 MySQL/HTTPS/DeepSeek，两者分开统计。
