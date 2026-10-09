# AI Memories 本机后端

本目录是从用户提供的 backend.zip 解压后完成融合的服务端。SwiftUI 客户端调用 FastAPI，服务端连接独立 MySQL，并在服务端调用配置的 AI。接口契约见上级 `contracts/openapi.json`；变更报告和验证记录已移至桌面的 `ai memory-supporting-materials/`。

## 本机已配置的服务

- API：`http://127.0.0.1:8000`；接口页面：`http://127.0.0.1:8000/docs`；健康检查：`http://127.0.0.1:8000/health`。
- MySQL：`127.0.0.1:3307`，独立数据库 `ai_memories_local`，数据目录 `.runtime/mysql`。
- API 与数据库由当前用户的 macOS LaunchAgents 保持运行；登录后自动启动。电脑睡眠、关机或退出登录期间不提供服务。
- 当前是本机、单家庭开发模式；绑定回环地址，没有账号登录与多用户权限系统。

在此目录执行：

```sh
.venv/bin/python scripts/manage_local.py status
.venv/bin/python scripts/manage_local.py start
.venv/bin/python scripts/manage_local.py restart api
.venv/bin/python scripts/manage_local.py stop
```

`stop` 卸载当前登录会话中的服务，保留数据和 plist；下次登录仍会自动加载。要取消登录自动启动，在停止后将 `~/Library/LaunchAgents/com.aimemories.local.api.plist` 和 `com.aimemories.local.mysql.plist` 移出 LaunchAgents 目录。

## 在另一台 Mac 初始化

需要 Python 3.12、MySQL 8 和 Xcode。`manage_local.py` 默认 MySQL 安装于 `/usr/local/mysql`，仅管理本项目自己的 3307 端口实例。以下初始化命令仅适用于尚无 `.runtime/mysql` 数据的全新副本，已有数据库不要重新初始化。

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写自己的 AI 密钥、模型和兼容接口地址。
mkdir -p .runtime/mysql .runtime/logs
/usr/local/mysql/bin/mysqld --no-defaults --initialize-insecure --basedir=/usr/local/mysql --datadir="$PWD/.runtime/mysql"
.venv/bin/python scripts/manage_local.py start mysql
# 等待 MySQL 初始化完成，可查看 .runtime/logs/mysql-error.log。
.venv/bin/python scripts/bootstrap_database.py
.venv/bin/alembic upgrade head
.venv/bin/python scripts/manage_local.py start api
```

已存在的 MySQL 可自行创建数据库，在 `.env.local` 设置 DATABASE_URL，再运行 Alembic 和 API；无需运行本地 MySQL 初始化脚本。生产环境需自行配置 HTTPS、认证授权、访问控制、备份和监控。

`.env` 的 AI 配置和 `.env.local` 的本机数据库密码只在当前机器，均未打包进交付源码。启动配置中没有密钥。迁移工具使用同一套环境变量。`requirements.txt` 是本次实际安装成功的版本锁定文件。

## 验证

```sh
# 18 项既有测试 + 6 项 FastAPI/MySQL 异常注入测试（AI 被测试替身替换）
.venv/bin/pytest -q tests/test_chat_prompt.py tests/test_chat_send_message.py tests/test_memory_service.py tests/test_workflow_integration.py
# 真正调用配置的 AI，会消耗接口额度；创建带“自动联调测试家庭”标识的独立数据
.venv/bin/python scripts/smoke_fullstack.py
# 先执行上一条，再验证两个服务重启及并发读取
.venv/bin/python scripts/verify_restart.py
```

照片当前每段回忆最多一张、上限 8 MB；服务端解码、校验并重新编码为 JPEG 后存入 `.runtime/media`，数据库保存关联和路径。AI 当前只处理文字，照片作为回忆附件，不进行视觉识别。提交相同请求 UUID 可安全重试。并发锁用于单进程，所以本机启动脚本固定 `--workers 1`，请勿直接扩成多 worker。
