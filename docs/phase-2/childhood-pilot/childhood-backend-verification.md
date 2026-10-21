# 童年采访真实后端：验证与人工审核材料

2026-10-14。状态：真实后端试点已实现，云端隔离验证完成，等待人工审核；未提交、推送或更新生产服务。B04改动继续暂停。本块计划见[接入计划](childhood-backend-pilot-plan.md)。

## 本次结论

采访已从独立Prompt原型接入实际FastAPI、MySQL、消息、草稿和确认保存接口。六段固定童年资料走完真实流程，回忆真正写入测试数据库，保存后才进入下一题，重试不会重复创建消息／回忆。普通路径比原型中反复总结和重复邀请更可控。

**这证明后端试点可用，不代表已经完成正式产品的人机体验验收。** 本次仍为固定虚构人物和脚本回答，没有真人语音或突然插入其他故事；前端尚未增加童年模式入口。实际App默认聊天与生产服务继续沿用原方式。

## 改动与行为

| 改动 | 实际行为 |
| --- | --- |
| 新建会话可选`interview_module=childhood` | 进入童年六题试点；默认请求不改变已有会话行为 |
| 状态写入现有information JSON | 保存当前题、阶段、证据字段、实际动作／连接、已问／已答／不可答目标及模块进度，无新增DDL迁移 |
| 回答AI只验收局部目标 | 原话仍完整交事件AI；未知不等于信息取得 |
| 事件AI提供证据，不直接生成对外问题 | 控制器计算字段与过程阈值，按一个目标渲染问题，避免一个问句塞进两个目标 |
| 已有事实与过程保留 | 短答不能将已核对事实清成missing；明确更正须带本轮原文依据 |
| 最多一次同目标澄清 | 同一叶子目标已问两次仍未取得，则不继续循环，允许按已有材料整理，不标作完整 |
| 明确流程阶段 | 初次邀请补充→接住补充→核对草稿→真实确认保存→下一故事；保存成功才增加计数 |
| 模块检查 | 控制器按独立保存ID和最低字段计算数量；模型只提出有证据的疑似重复／关键矛盾，至少5件合格素材才给可整理提醒 |

`scope`表示本人通过创建请求选择童年范围，是用户选择的上下文，不是AI从口述推算出的年份；写稿仍只使用有用户原话来源的事实。

核心源码：[控制器](../../../cloud-deployment/backend/app/services/guided_interview.py)、[字段与状态](../../../cloud-deployment/backend/app/schemas/guided_interview.py)、[实际Prompt](../../../cloud-deployment/backend/app/ai/guided_prompts.py)、[工作流接入](../../../cloud-deployment/backend/app/services/workflow_service.py)。

## 实际验证

### 真实MySQL与FastAPI回归

最终云端候选检查：**301 passed**，包含旧后端回归及12项新增检查。

新增检查覆盖引用原文、跨事件动作拒绝、短答保留事实／过程、请求／分工不作为实际操作、相处中的本人参与、未知停止、已答不重问、变化信息复用、澄清次数限制、真实API持久化与幂等重试、草稿保存后下一题、失败时原文保留。

回归模型为可控替身，数据库和接口为真实服务；下方另列真实DeepSeek测试，二者不混作一个通过结果。

首次回归发现旧草稿校验值兼容性问题，已通过“非试点会话不序列化空的guided_interview字段”修复。另一个失败来自测试替身把dict直接赋给类型化引用，已修正替身。中间一次部署脚本语法错误发生在测试之后、服务启动之前，修复后重新完成回归与部署；未影响生产。

### 真实DeepSeek与真实HTTP

独立数据库和服务共56个HTTP请求，0个HTTP错误。覆盖如下：

| 故事 | 实际行为 |
| --- | --- |
| 灶间日常长答 | 一次覆盖已有经过，直接邀请补充，不逐项重问 |
| 书袋相处短答 | 对初始口述追问，收到“我试背了”后进入补充；再补敞口无拉链，回复明确接住补充 |
| 捕鱼后续记不清 | 关闭经过追问，允许整理已知片段；保存了素材，但未计入合格故事 |
| 收谷劳动长答 | 本人操作和父亲分工保持区分，进入补充与草稿 |
| 搬家长答 | 前后住处与操作直接复用，不另追未知搬家原因 |
| 漏雨长答 | 已有放盆、挪盆的局部过程，不强索事情最终结局 |

六份草稿均调用实际写稿模型，并分别经过确认接口保存为六条数据库回忆。确认重试返回同一memory_id，没有重复回忆。每条保存后通过人物会话接口开启下一题。模块收尾后状态为finished，保留6件已保存素材、5件达到最低标准素材，chapter_ready=true。

9次实际需要模型判断的消息请求耗时**2.079–3.843秒**；该测量在云服务器本机HTTP入口完成，包含后端模型调用、校验和数据库处理，不含用户手机至服务器的网络／界面显示。6次实际草稿生成为0.918–1.326秒。其余“没有补充了”、保存重试等控制回复无需再次调用模型。

状态快照共核对496处原话引用（含重复快照），未发现来源ID或逐字片段不匹配；这不是496个独立语义测试，动作分类与连接仍需要语义复核。

### 重启与恢复

1. 完成六段后重启本次隔离API：保存计数、合格计数、成章提醒和finished状态完全一致。
2. 另建一个尚在追问的试点会话，暂停、重启，再继续：已知事实、动作、连接、待答问题、已问／已答／不可答目标均一致，恢复后呈现原问题。

这两项确实重启了本次隔离服务，不只是在同一个进程中GET一次。没有重启生产或B03服务。

## 阅读实际稿件

- [纯AI与人问答](examples/childhood-backend-dialogue.md)
- [问答与逐项后端状态](/Users/student03/Desktop/shinian-validation/artifacts/archive/phase-2/childhood-pilot/raw-documents/childhood-backend-http-qa.md)
- [实际六份草稿](examples/childhood-backend-drafts.md)

问答来自接口返回，保存为真实数据库操作；草稿未经手工润色。重复HTTP请求没有伪装成新的真人问答。

## 尚需产品判断的部分

- 书袋在“做袋→试背”后已满足最低规则，预设的下一段“带子太长、母亲改短”没有发送给后端；脚本没有强塞更丰富答案来包装成功。这段草稿确实较短，说明最低完整标准与故事丰满程度还需区分。
- 对外问题现在可控制为一个目标，但固定模板的语气与节奏需要真人试用；并非已验证所有老人觉得自然。
- 动作／先后的语义仍由模型抽取。引用和计数正确不等于语义一定正确，本例不能证明任意回答都稳健。
- 只接入童年试点，不是全部37题、七题骨架、多模块选择与自由插话的完整产品实现。
- 本轮没有验证真机语音、PDF排版或新前端入口。没有iOS/UI代码变更；新增后端模式的前端联调留待接入入口时执行。

## 环境与原始证据

候选服务：`shinian-childhood-isolated`，服务器`127.0.0.1:18004`，独立数据库前缀`shinian_childhood_live_`。镜像`sha256:d5dd2723a3669113d814e3b9ce153f7f993cd88c8ead29b92a372aafe9cdf0eb`。云端60个app Python文件的SHA256与本地源码一致。

生产`backend-api-1`镜像仍为`sha256:5d02956a447fb7b51e688cffddf9ca38833aed24805c34960f912261967fc991`；B03隔离服务仍为`sha256:223d80f85085c44c731735a49a2b7a489aa915a11415dac5c43b7c46daf9412c`，均保持运行。

验证资料位于`/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/`：

- [回归与部署日志](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/cloud-verification.log)
- [真实HTTP原始日志](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/live-http.jsonl)
- [HTTP统计](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/live-summary.json)
- [完成状态重启检查](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/restart-verification.json)
- [未完成问题重启检查](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/active-restart-verification.json)
- [源码一致检查](/Users/student03/Desktop/shinian-validation/artifacts/childhood-backend/source-verification.json)

复核入口为现有`POST /api/v1/chat/sessions`，创建时增加`interview_module=childhood`并提供同一家庭的主要人物。消息、草稿和确认保存仍使用原接口。测试脚本和新增回归在验证仓库，不属于老师构建入口。

本块目前等待人工审核。正式提交只应包含本块后端与说明文档，不包含暂停的B04修改、其他未跟踪项目规则或云端测试数据。
