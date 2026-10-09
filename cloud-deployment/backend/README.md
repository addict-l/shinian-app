# 拾年云端后端

正式后端运行在阿里云服务器，使用 FastAPI、MySQL、Docker Compose 与 Nginx HTTPS。老师在 Mac 上只需按项目根 README 启动 iOS 前端并登录现有家庭账号，无需部署本机数据库或后端。

## 职责与目录

- `app/api/`：家庭人物、对话、回忆和照片 HTTP 接口。
- `app/services/`：对话重试、草稿确认与照片保存规则。
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

参考 [阿里云部署说明](DEPLOY_ALIYUN.md) 和 [部署记录](../../docs/cloud-deployment-record.md)。生产 `.env.production`、家庭认证文件及密钥只保存在服务器，不能加入 Git 或镜像。部署前备份数据库和照片；每次云端运行验证通过后，在服务器本地 Git 中提交，再提交与推送 Mac 工程。Git 回退代码不等于回退数据库或正在运行的镜像。

当前工作流依赖进程内会话锁，因此 API 固定 `--workers 1`。多进程或多实例需要先改用跨进程锁及对应验证。

## 开发验证

测试源码、验证脚本和产物保存在主工程同级的 `shinian-validation`。云端使用独立候选镜像、随机测试库及测试模型；正式家庭数据库不执行测试清理，真实照片与业务备份不放进主工程。测试通过后，再更新正式容器并检查健康、迁移、对应接口和 HTTPS。

`manage_local.py` 与 `bootstrap_database.py` 是保留的旧本机开发工具，不属于老师启动 App 的步骤；当前正式后端全部在云端运行。
