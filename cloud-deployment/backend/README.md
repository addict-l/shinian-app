# 拾年云端后端

正式后端运行在阿里云服务器，使用 FastAPI、MySQL、Docker Compose 与 Nginx HTTPS。老师在 Mac 上只需按项目根 README 启动 iOS 前端并登录现有家庭账号，无需部署本机数据库或后端。

## 职责与目录

- `app/api/`：家庭人物、对话、回忆、照片和人物回忆录 HTTP 接口。
- `app/services/`：分析与对话模型协作、重试、草稿确认、回忆维护、照片与版本化回忆录设置规则。
- `app/models/`、`repositories/`：数据库模型和数据读取。
- `app/schemas/`：前后端契约及输入校验。
- `alembic/`：兼容数据库迁移。
- `docker-compose.demo.yml`：MySQL 和单 worker API；API 端口仅绑定服务器回环地址。

照片保存在 Docker 媒体数据卷中，数据库保存其会话、消息及回忆关联。客户端通过带家庭认证的 API 请求加载照片。

## 多图消息

1. 每张照片先上传到 `POST /api/v1/chat/sessions/{session_id}/media?client_request_id={uuid}`。上传是追加操作，重试保留相同 UUID 与相同图片数据；不同内容复用同一 UUID 返回冲突。
2. 全部照片上传成功后，向消息接口提交 `content`、有序的 `attachment_ids` 和稳定的 `client_request_id`。每条最多 9 张，文字与照片至少有一项。照片在数据库事务中关联到该消息。
3. 纯照片消息返回固定提示，不调用 AI，也不改变信息完整度。文字加照片时只把文字交给 AI，照片和纯照片提示不进入模型输入。
4. 上传或模型失败时保留已有内容；同一请求重试不会重复创建消息和照片。消息状态可以通过 `GET /api/v1/chat/sessions/{session_id}/state` 读取。
5. 已发送照片不从输入区删除。单张未发送照片可通过 `DELETE /api/v1/chat/sessions/{session_id}/media/{media_id}` 移除；旧版批量移除接口只清理未关联消息的附件。

单张上传不超过 8 MB。服务器校验图片格式、像素量并重新编码为 JPEG，处理方向、限制尺寸、去掉元数据。App 上传前压缩副本，相册原图不改动。第一阶段不做图片识别。

## 部署与版本维护

参考 [阿里云部署说明](DEPLOY_ALIYUN.md)、[一期部署快照](../../docs/phase-1/records/cloud-deployment-record.md)与[二期部署记录](../../docs/phase-2/records/cloud-deployment-record.md)。生产 `.env.production`、家庭认证文件及密钥只保存在服务器，不能加入 Git 或镜像。部署前备份数据库和照片；每次云端运行验证通过后，在服务器本地 Git 中提交，再提交与推送 Mac 工程。Git 回退代码不等于回退数据库或正在运行的镜像。

当前工作流依赖进程内会话锁，因此 API 固定 `--workers 1`。多进程或多实例需要先改用跨进程锁及对应验证。

## 开发验证

测试源码、验证脚本和产物保存在主工程同级的 `shinian-validation`。云端使用独立候选镜像、随机测试库及测试模型；正式家庭数据库不执行测试清理，真实照片与业务备份不放进主工程。测试通过后，再更新正式容器并检查健康、迁移、对应接口和 HTTPS。

`manage_local.py` 与 `bootstrap_database.py` 是保留的旧本机开发工具，不属于老师启动 App 的步骤；当前正式后端全部在云端运行。

## T07 交付版本

本节与交付清单是第一阶段 T07 时的快照，后续模型与业务变化见[第二阶段资料](../../docs/phase-2/README.md)。

GitHub 包含完整可构建后端、固定依赖、全部迁移及示例环境，业务 Python 源码与正式运行 API 逐项核对。实际镜像、迁移与组件源码哈希见 [交付版本清单](../../docs/phase-1/t07/delivery-manifest.json)。Nginx 配置示例位于 ../nginx/aimemory.conf.example；完整部署与备份步骤见 DEPLOY_ALIYUN.md。生产配置、家庭密码、证书私钥和数据库／媒体备份由维护者单独管理，老师运行现有云端不需要获得这些部署凭据。

## 采访新流程（可选）

`INTERVIEW_PIPELINE=v3j_v4d` 让访谈入口和人生骨架改用判定层 v3j（`app/ai/contract_interview_v3j.py`）和说话层 v4d（`app/ai/interview_speaker.py`），运行合同在 `app/ai/interview_runtime_v3j_v4d/`，流程在 `app/services/contract_v3j_interview.py`（访谈入口）和 `app/services/contract_v3j_life_overview.py`（人生骨架）。默认 `v2` 即现网。按题标记流程，已开始的题不换流程。环境变量、启用与回退见[部署说明](DEPLOY_ALIYUN.md#采访新流程开关v3j--v4d)，业务差异与离线验证见[采访链路优化台账](../../docs/phase-2/interview-optimization/README.md#接入后端v3j--v4d)。

## 普通访谈的可选快速通道

`LLM_MODEL` 继续用于开场、草稿及其他既有职责。设置 `LLM_TURN_MODEL=qwen3.7-flash` 后，普通文字发送将原文信息分析和完整自然回复合并为一次非思考、严格结构化请求，保留完整原文及事实、策略校验；留空沿用原串行流程。所选模型必须支持百炼兼容接口的 `json_schema` 严格输出。

设置 `LLM_TURN_PARALLEL=true` 后，每轮同时发出两份请求，只采用第一份通过原文依据、信息矛盾、就绪和回复策略校验的结果。模型线程不写入数据库，迟到结果不会添加消息或改动已经返回的回复。最新输入不超过 200 字时，禁用 SDK 自动重试、单次网络超时为 6 秒；更长的讲述保留原 45 秒网络超时及一次 SDK 重试。网络超时是 SDK 各阶段等待设置，不是端到端总时限。结构或依据错误最多修正一次；两份均失败时保留用户消息，沿用同一请求 ID 重试去重。正在运行的另一份请求仍可能完成并产生费用，通常为两次调用，短回复发生结构修正时最多四次，长文还可能发生 SDK 重试。

上述配置是显式启用项，不能保证供应商每轮都在 6 秒内完成。启用后服务启动时提前建立 SDK 及可复用连接，通过最多两次有界 `models.list` 请求准备并行连接；不传故事、不调用模型生成，失败只记录异常类型并继续启动。当前用户要求普通短回复完整返回不超过 6 秒、长篇讲述及长草稿不超过 10 秒，按预先标注的类别逐条验收。部署时须记录候选模型、完整回复计时与调用用量，并单独取得生产发布授权。关闭并行可保留单次合并请求；清空 `LLM_TURN_MODEL` 可回到原分析、对话流程。

并行启用时，可选 `LLM_TURN_SECONDARY_MODEL=qwen3.7-plus`，使第二份请求使用更强的模型；留空使用两份相同模型，关闭并行后不调用第二模型。两条分支各自使用独立配置副本，仍以第一份通过校验的结果为准。Flash 与 Plus 的标价不同，同等 Token 量下，一份 Flash 加一份 Plus 约为两份 Flash 的 5.5 倍标价估算，不能把请求数仍为两次理解为费用相同；失败调用的实际账单需要供应商核对。

`LLM_DRAFT_MODEL` 可单独指定支持严格 JSON Schema 的非思考草稿模型；留空继续使用全局模型。配置后草稿调用采用 10 秒网络阶段超时、关闭 SDK 自动重试，依据错误仍有一次有界修正；此设置不是完整草稿的耗时保证。草稿使用经过连续原文校验的 `narrative_sources` 保留完整经过，不局限于六项摘录；用户更正内容仍过滤，有拒绝字段时保守使用独立采集的事实摘录，避免把拒绝内容从长段原文重新带入。旧草稿在没有新增叙事来源时保持原来源摘要标识，继续支持既有确认及手改保护流程。

### DeepSeek V4 Flash

DeepSeek 当前 API 使用 `https://api.deepseek.com`，模型名为 `deepseek-flash`；官方仍接受旧名 `deepseek-v4-flash`，但会路由至当前 Flash 版本。Chat Completions 使用 JSON Object 输出与 `thinking: disabled`，再由应用进行完整 Pydantic 和原文证据校验；不能向该接口发送通义专用的 `enable_thinking` 或 `json_schema` 参数。通用环境变量 `LLM_API_KEY` 和 `LLM_BASE_URL` 优先于旧 DashScope 变量，便于逐步迁移。

`python3 scripts/configure_deepseek_cloud.py stage` 会在本地隐藏读取并确认 API Key，验证 `/models` 与一次最小 JSON 请求，再通过 SSH 标准输入写入云端权限 `0600` 的 `.env.deepseek.pending`。它不会重启线上 API。兼容后端部署完成后执行 `python3 scripts/configure_deepseek_cloud.py activate`：脚本先确认运行镜像含 DeepSeek JSON 兼容，再备份当前 `.env.production` 与镜像标识，原子更新 API 配置并重启 API；健康检查失败时自动恢复旧环境文件并重启。Key 不进入 shell 参数、命令历史或脚本输出。旧别名与当前模型说明见 [DeepSeek 模型文档](https://api-docs.deepseek.com/quick_start/pricing/) 和 [Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

用户已接受并行访谈增加的调用费用。`stage` 会同时设置 DeepSeek 的主/备访谈模型与独立草稿模型，并启用 `LLM_TURN_PARALLEL=true`、`LLM_TURN_STRATEGY=parallel_tasks`。若 DeepSeek 已激活而只需恢复此策略，可运行 `python3 scripts/configure_deepseek_cloud.py optimize`；它复用现有密钥，不要求再次输入。

`LLM_TURN_STRATEGY` 默认 `race`，使用上述两份完整候选竞争。设置为 `parallel_tasks` 且开启并行时，两请求分别负责原文分析和自然采访；分析使用 `LLM_TURN_MODEL`，采访使用第二模型（留空则同模型）。两任务全部完成后才按实际事实和策略校验、发布回复，分析失败不发布采访文字。若采访需修正，仅重新生成小型回复，不重复分析已通过的事实。纯暂停与已就绪后的明确整理指令可直接依据已校验状态回应，不进行新推断、不生成或自动保存回忆；存在未分析讲述时禁止这个快捷路径。

分工模式的事实分析只接收当前故事的原文及已验证信息。采访线程依据用户原文和已有策略提前校验、修正文字，与事实分析同时进行；该临时检查不授予生成资格，两个任务结束后仍按实际新信息完整校验。后置采访修正携带具体校验原因，使用紧凑的实际事实与策略，避免重新猜测错误原因。普通轮次通常两次调用；两个初始任务各有一次结构修正，采访在实际策略校验后还可能有一次两轮修正，因此关闭 SDK 重试时单轮最多六次模型调用。需要按日志实测修正率和费用，不能套用竞争模式的四次上限。

API 连接池保留空闲连接最多 120 秒以减少重复建立连接，维持 TLS 校验。紧凑 JSON 只减少格式空白及空的可选字段，不省略六项维度或实际事实。最终回复可去掉无原文依据的评价、保留一个通过规则检查的问题；没有合格回复时仍使用有界修正或返回错误，所有事实、数字、原文范围和保存策略检查保持有效。

分工分析省去重复的完整聊天历史；较早的用户消息仍以按原顺序排列的完整片段及对应上一问传入，最新原文保持完整，用于本轮意图检查。原文范围最终在服务端完整消息上解析、校验。明确的“补充一下”事实若在失败请求后尚未分析成功，会在后续分析时继续保留其真实来源，不能因最新消息只是整理命令而丢掉补充。相对时间、同地点的明确承接保留原记录时间和地点，不推算新日期；具体日期矛盾及用户更正仍按既有规则处理。
