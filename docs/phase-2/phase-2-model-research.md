# 第二批次百炼模型调研

查阅日期：2026-10-12 至 2026-10-13（Asia/Shanghai）。状态：已按用户后续要求接入 DeepSeek Flash，并完成隔离候选实测和正式云端配置；实际账单未读取。原百炼官方价格资料保留为历史候选估算，不代表 DeepSeek 价格。

## 当前能确定的结论

先比较四组：`qwen-plus` 基线、`qwen3.7-flash` 成本候选、`qwen3.7-plus` 均衡候选、`qwen3.8-max` 质量上限候选。后三者已列在本次实际打开的官方页面中；因此不把较早的 Qwen3 名单当作最新名单。候选代表不同取舍，并不代表已经证明更适合本产品。

仓库公开的《阿里云部署操作记录》写有 `LLM_MODEL=qwen-plus`；这只能作为历史基线线索，不能证明阿里云当前进程的模型配置。正式对比前应核对运行模型 ID、接口、地域、思考开关和请求次数，只记录无敏感信息的配置摘要。

用户最初要求普通短对话完整回复不超过 5 秒，随后明确接受 5–6 秒；当前上限为 6 秒。官方能力、限流上限及 Token 生成速度不能证明本应用达标。模型质量和速度都需要同场景对比，且不能通过删掉必要追问或使用空泛短回复来达标。

## 候选与用途

下表“测试用途”是项目建议，尚未验证。

| 候选 | 已核对的官方信息 | 测试用途 |
| --- | --- | --- |
| `qwen-plus` | 文本模型；1M 上下文；北京支持结构化输出。[模型文档](https://help.aliyun.com/zh/model-studio/qwen-plus) | 保留基线，区分提示词/链路改进和模型升级的贡献 |
| `qwen3.7-flash` | 1M 上下文；北京支持结构化输出；价格页列出对应快照 `qwen3.7-flash-2026-07-15`。[模型文档](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[价格页](https://help.aliyun.com/zh/model-studio/model-pricing) | 短访谈和轻量边界判断，优先验证能否同时满足质量与延迟 |
| `qwen3.7-plus` | 1M 上下文；北京支持结构化输出；官方说明功能等同 `qwen3.7-plus-2026-05-26`。[模型文档](https://help.aliyun.com/zh/model-studio/qwen3-7-plus) | 自然访谈、信息完整性判断、长篇草稿中度整理 |
| `qwen3.8-max` | 1M 上下文；存在 `qwen3.8-max-0902` 快照；支持结构化输出。[模型文档](https://help.aliyun.com/zh/model-studio/qwen3-8-max) | 长篇草稿和复杂事件边界的质量上限对照，不预设其能满足短对话 5 秒 |

为复现结果，评测应记录精确 ID。使用滚动别名与固定快照可能有不同限流或权限，不能只换名称后假定行为相同。

## 思考与结构化输出

Qwen3.7 Plus、Qwen3.7 Flash、Qwen3.8 Max 均属于混合思考模型，官方文档标明默认开启思考；可显式传 `enable_thinking=false` 关闭。官方也说明思考会增加生成 Token 与总耗时。首轮四组统一使用非思考模式；若后续长篇任务需要思考，再单独增加对照组。OpenAI 兼容 SDK 中该字段是扩展参数，传递方式取决于 SDK；DashScope 原生接口的位置另有规定，不可照搬。[深度思考文档](https://help.aliyun.com/zh/model-studio/deep-thinking)

官方区分 `json_object` 与 `json_schema`：前者保证 JSON 语法，不保证业务结构；后者可约束字段和类型。支持名单包含 Qwen3.7 Plus、Qwen3.7 Flash、Qwen3.8 Max，`qwen-plus` 列在非思考 JSON Object 名单，未列在本页 JSON Schema 名单。建议新候选的纯文本分析使用 Schema；基线保留 Object 后做字段校验。多模态输入的 Schema 约束可能降级为 Object，不能假定照片分析有相同保证。[结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

即使 Schema 有效，仍应校验事实来源、时间归属和枚举语义。正文不因为字段齐全就被视为事实正确；AI 只提醒事件边界，不负责自动拆篇或保存。

## 价格对照

以下为华北2（北京）普通实时调用原价，单位人民币元/百万 Token；不含活动、缓存、Batch、免费额度或其他服务费用。官方表格按单次输入长度给出档位，测算时需匹配该档位。价格可变，采用前核对用户实际地域和控制台账单。[官方价格规则](https://help.aliyun.com/zh/model-studio/model-pricing)

| 模型 | 单次输入 Token 档位 | 输入 | 非思考输出 | 思考输出 |
| --- | --- | ---: | ---: | ---: |
| `qwen-plus` | ≤128K | 0.8 | 2 | 8 |
| `qwen-plus` | >128K，≤256K | 2.4 | 20 | 24 |
| `qwen-plus` | >256K，≤1M | 4.8 | 48 | 64 |
| `qwen3.7-flash` | ≤32K | 0.2 | 0.8 | 0.8 |
| `qwen3.7-flash` | >32K，≤256K | 0.6 | 2.4 | 2.4 |
| `qwen3.7-flash` | >256K，≤1M | 1.2 | 4.8 | 4.8 |
| `qwen3.7-plus` | ≤256K | 2 | 8 | 8 |
| `qwen3.7-plus` | >256K，≤1M | 6 | 24 | 24 |
| `qwen3.8-max` | ≤1M | 12 | 36 | 36 |

对应价格来源：[Qwen Plus](https://help.aliyun.com/zh/model-studio/qwen-plus)、[Qwen3.7 Flash](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)、[Qwen3.7 Plus](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)、[Qwen3.8 Max](https://help.aliyun.com/zh/model-studio/qwen3-8-max)。思考模式即使输出单价相同，额外推理 Token 仍增加总费用。

地域不能混用。例如新加坡“国际”部署：Flash 三档输入/输出为 0.225/0.974、0.749/2.998、1.499/5.995；Plus 两档为 2.998/11.991、8.993/35.972；Max 为 14.988/44.965。以上各自来自同名模型文档的新加坡章节。北京价只用于统一比较，不能据此推断用户当前账单。

官方总价格页在本次查阅时展示 Plus 限时优惠，而模型单页明确只展示原价；本文统一用原价估算，优惠有效期及用户是否适用尚未核实。[价格总页](https://help.aliyun.com/zh/model-studio/model-pricing)、[Plus 模型单页](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)

计算示例（假设非思考、未命中缓存、每次只有一个模型调用；是测算而非真实会话用量）：

| 输入 / 输出 Token | Plus 基线 | 3.7 Flash | 3.7 Plus | 3.8 Max |
| --- | ---: | ---: | ---: | ---: |
| 4,000 / 200 | ¥0.00360 | ¥0.00096 | ¥0.00960 | ¥0.05520 |
| 20,000 / 3,000 | ¥0.02200 | ¥0.00640 | ¥0.06400 | ¥0.34800 |

计算式为 `输入数×输入单价/1,000,000 + 输出数×输出单价/1,000,000`；一轮若含分析、对话、重试等多次调用，应把每次费用相加。

## 建议的评测和采用顺序

这是待实现方案，不是已通过验收的结论。

1. 使用同一组虚构或独立测试家庭场景、同一非思考设置，同时保留当前提示词和修订提示词两个基线，记录模型 ID、输入/输出 Token、重试和 HTTP 错误。
2. 评测自然访谈：用户讲具体转折时，能沿着转折追问；不要每轮固定复述总结再提问；每轮最多一个问题；用户想暂停或记不清时应尊重，不诱导添加事实。
3. 评测事件边界：区分同一事情的前因后果与另一件独立经历；只自然提醒，不自动拆篇，不把两件事混成一个标题或时间。加入回到前一事件、时间不明、人物相同但地点不同等反例。
4. 评测长篇草稿：调整叙事、去重、删除赘述，保留关键经过、个人语气和不确定性；不能用文学描写补造细节或把提醒的两件事合成一件事。
5. 端到端速度从手机发送点击到完整有效回复显示计时；另测后端、分析、对话、重试与网络时间。分别报告每条结果、p50、p95、失败率与超过原 5 秒及当前 6 秒的次数。流式首字快不能替代完整回复目标；短对话也应覆盖历史较长的会话。
6. 先看单一模型是否能同时达标。若不同职责确有明显收益，再评估分模型：Flash/Plus 负责对话及必要分析，Plus/Max 负责显式草稿整理。不要为每轮堆叠多个串行调用；缓存或合并是否可行要结合状态正确性验证。
7. 用盲评结果、端到端耗时与总费用选方案；模型切换仍需遵循本项目提交/设计/验证流程。未通过质量和完整回复速度检查前，不更新正式服务。

## 仍需核实

- DeepSeek 云端配置、结构化 JSON 调用、模型授权与当前候选场景均已实测；账户实际地域价格、优惠及账单未核对。
- 21 个合成场景通过后，用户已检查问答材料并明确允许提交 B01/B02；本次采用 DeepSeek Flash（ds flash）。
- 日常流量、账户并发限额与长期延迟波动需要上线使用后通过不含敏感数据的运行指标持续观察。

## 获取记录

按 agent-reach 路由先尝试 Exa CLI 与 Jina 网页阅读：`mcporter` 不存在，Jina 两次网页读取在 30 秒内未返回正文；随后用网页工具实际打开上列阿里云官方页面，未采用二手文章或搜索摘要替代原文证据。网页可随时更新，部分页面更新时间字段未返回，本文只记录实际查阅日期。`agent-reach check-update` 返回 v1.5.0 已为最新版。

## B01 实测进展

生产只读核对为 `qwen-plus`、入口 `dashscope.aliyuncs.com`。原串行合成样本16.839秒；关闭思考对照15.863秒；`qwen3.7-flash` 原两段调用7.526秒。合并单次仍有波动，第23问用户接受双请求并行，后来明确允许5–6秒完整回复。正式候选首轮8次完整HTTP测量3.221–5.886秒，保留原5秒未达标记录。

候选为 `LLM_TURN_MODEL=qwen3.7-flash`、`LLM_TURN_PARALLEL=true`、`enable_thinking=false`；开场与草稿保持全局模型。`qwen3.8-flash` 早期快速输出漏事实，要求完整事实后不稳定，未采用；`qwen3.7-plus` 合并样本6.67秒。以上诊断样本不能证明长期延迟或访谈质量。实际Token、失败和修正次数保存到仓库外验证材料，标价估算不等于实际账单。

## 用户指定 DeepSeek Flash 与 B02 实测（2026-10-13）

用户之后明确指定更换为 DeepSeek V4 Flash，并已将 API Key 通过隐藏输入脚本安全暂存及验证。本项目实际配置采用当前 API model ID `deepseek-flash`、兼容端点 `https://api.deepseek.com`；JSON Schema 专用响应格式改为 JSON Object，再由应用侧 Pydantic、来源和访谈策略验证。官方接口说明见 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

B02 在 DeepSeek 并行访谈/草稿配置下完成 21 个合成云端场景：21 个 HTTP 回复均在 6 秒内，长篇回应及长稿均在 10 秒内；最慢短请求 2.283 秒，最慢长稿 2.114 秒。37 次模型调用全部成功，累计输入 116,939 tokens、输出 2,366 tokens。此处只记请求量，不推算实际账单；未读取账户价格、优惠或账单。当前生产模型及并行配置见 [B01/B02 部署记录](records/cloud-deployment-record.md#b01b02-deepseek-flash-部署2026-10-13)。
