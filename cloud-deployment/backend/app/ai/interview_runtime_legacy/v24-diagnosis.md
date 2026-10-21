# v1.24 通用修复诊断

本候选从冻结的 candidate27-response-actor 复制；原目录和真实 DS 运行未改动。新目录不包含 manifest，交由主任务审查后冻结。以下为本地合成验证，不代表真实 DS 或随机三轮验收通过。

## 修复边界

- 人际应对：真实子问、target_field_id、focus 仅提供语境，不能豁免目标核对。按子句核对主体、外层动作的实施状态及同一矛盾关系。伴侣抱怨、对方要求／希望、假设行动不能冒充已采取的做法；value 单取请求中的动作时仍检查完整引用的框架。
- 实际沟通和未成功状态：已经解释、询问、劝慰、商量本身是行动；其内容含抱怨、希望或请求不删除整句。实际自我行动、双方商量、对方道歉、为双方寻求调解、拒绝、未处理、未解决、停止争吵和提议不了了之按原意保留。纯未来愿望和未知后续不补造结果。value 若只选抱怨，不能用另一子句的动作洗成有效答案。
- 原文自问自答：如果设问是省略对象的必要关系依据，A/B 同时保留原文设问与回答，value 可仅保留答案；不是所有短答都要求新增上下文。
- 亲友相处：“邻里或亲友”一类充分即可；同住亲属及姻亲仍可属于亲友。只有身份、同住或家境不证明相处氛围。补入 CH06-E1 合同，并要求 B 不因类别重叠删除已有充分答案。
- 真实问答省略：原历史问题回顾已发生的转向时，回答若承接该转向并讲当时选择、做法或后来的实际实践，可用原问理解省略对象；不要求重说行动全名。题干独有事实、纯愿望／担心／评价不能代填实际选择。A/B 使用相同通用规则。
- 发布重建：builder 在各祖先目录依次查找 interview-development-baseline.md 与 docs/interview-development-baseline.md；找不到明确报错。未改题目、顺序、跨题边界或 gold。

## 留存的红绿测试

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 36 个合成正负短句，分别有／无定向语境 | C27 39/72 → C28 72/72 | v24-red-repro.json；v24-red-repro-final-fixtures.json；v24-delivery-probes.json |
| 5 个含抱怨／希望的实际沟通正例，分别有／无定向语境 | 中间实现 6/10 → 10/10 | v24-communication-red.json；v24-delivery-communication-probes.json |
| 56 个既有语义测试 + 10 个新测试方法 | 66/66，0 failure/error | v24-delivery-python-guards.json |
| 核心运行检查 | 181/181 | v24-delivery-node-guards.json |
| 62 题、193 要素合同边界 | 895/895 | all-contract-boundaries.json |
| 字段拒收／精度／联合证明／B 完整性 | 10/10、6/6、4/4、6/6 | v24-delivery-node-guards.json |
| 证据单元检查 | 通过 | v24-delivery-node-guards.json |
| 真实发布目录布局下生成合同 | JSON/Markdown 均逐字节一致；缺基准明确失败 | v24-delivery-contract-rebuild.json |

新增测试入口：`python3 -m unittest tools.test_interview_response_evidence_v24 -v`。

第一次红记录的“与同事商量值班”后来明确为“与同事之间的矛盾”，避免将可能帮助夫妻分工的工作调整误定义为负例。旧红记录完整保留，最终 36 条同一测试集也对原 C27 重新只读回放，结果仍为 39/72。

本守卫是有边界的语义拒收检查，并非完整自然语言解析器；未覆盖的句式仍须通过真实 DS 运行观察。代码没有人物、语料身份、gold 或测试集读取。尚未进行 C28 真实 DS 修复回归、随机三连轮验收、云端发布或 commit。
