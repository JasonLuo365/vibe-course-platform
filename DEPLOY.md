# Vibe Server Docker 部署文档

## 前置条件

- 已安装 Docker Engine + Docker Compose（推荐 Docker Desktop 或 Linux 发行版自带）。
- 拥有一个 OpenAI 兼容的 LLM API Key（示例默认 DeepSeek）。
- 端口 `8000` 未被占用（或自行修改 `docker-compose.yml` 的端口映射）。

## 部署步骤

### 1. 准备环境变量

```bash
cp server/.env.example server/.env
```

编辑 `server/.env`，至少修改以下两项：

- `VIBE_SESSION_SECRET`：改成随机长字符串，用于会话 Cookie 签名。
- `VIBE_LLM_API_KEY`：填入你的 DeepSeek（或其他兼容服务商）API Key。

数据目录 `VIBE_DATA_DIR` 与数据库 URL `VIBE_DATABASE_URL` 已在 `docker-compose.yml` 中固定为 `/data`，无需在 `.env` 中覆盖。

### 2. 启动服务

```bash
docker compose up -d --build
```

首次构建会拉取 `python:3.12-slim` 并通过 `uv` 安装依赖；后续更新代码后重新执行该命令即可增量构建。

### 3. 创建教师账号

容器启动后，使用 CLI 创建第一位教师（示例用户名为 `admin`，显示名为 `管理员`）：

```bash
docker compose exec -e VIBE_TEACHER_PASSWORD=你的密码 server vibe-server create-teacher admin 管理员
```

- 请把 `VIBE_TEACHER_PASSWORD` 替换为安全的初始密码。
- 后续可用同样命令创建更多教师账号。

### 4. 访问教师端

打开浏览器访问：

```
http://localhost:8000
```

使用第 3 步创建的教师用户名和密码登录。

## 备份与恢复

所有持久化数据都存放在 Docker 命名卷 `vibe-data` 中，包括 SQLite 数据库 `/data/app.db` 与学生提交包目录 `/data/packages`、`/data/extracted`。

### 备份

```bash
# 停止服务（可选，避免热备份时产生不一致）
docker compose stop

# 复制卷数据到本地目录
docker run --rm -v vibe-data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/vibe-data-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

# 重新启动
docker compose start
```

### 恢复

```bash
# 停止并清空当前卷（谨慎操作）
docker compose down
docker volume rm vibe-data

# 从备份恢复
docker run --rm -v vibe-data:/data -v $(pwd)/backup:/backup alpine sh -c \
  "cd /data && tar xzf /backup/vibe-data-YYYYMMDD-HHMMSS.tar.gz"

docker compose up -d
```

建议通过 cron/systemd timer 每日自动备份一次。

## HTTPS 建议

本镜像仅暴露 HTTP。生产环境或公网访问时，请在容器前放置反向代理终止 HTTPS。

### Caddy 示例

创建 `Caddyfile`：

```caddy
vibe.example.com {
    reverse_proxy localhost:8000
}
```

启动 Caddy 即可自动申请并续期 Let's Encrypt 证书：

```bash
caddy run --config Caddyfile
```

### Nginx 示例（已有证书）

```nginx
server {
    listen 443 ssl http2;
    server_name vibe.example.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 注意：学生端 CLI 在 HTTPS 证书校验失败时不会降级到 HTTP，请使用受系统信任的证书或让学生手动导入自签 CA。

## 学生端分发指引（摘要）

完整分发与安装机制见设计文档 §3《学生端：Codex Plugin（课程 Git Marketplace 分发）》。教师部署服务器后，向学生提供：

1. **课程 Marketplace 仓库地址**（GitHub 或 Gitee）。
2. **Bootstrap 命令**：引导学生安装 uv、注册 marketplace、写入学号与 `submit_token`。

### 纯 CLI 兜底命令

学生无需 Codex 插件也可直接提交作业：

```bash
uvx vibe-submit submit --code <作业码>
```

### Marketplace 注册示例

已安装 Codex CLI 的学生可执行：

```bash
codex plugin marketplace add <课程仓库URL>
```

之后即可在 Codex `/plugins` 页面安装课程插件，对话中说出“提交作业”由 MCP Server（`uvx --from vibe-submit==X.Y.Z vibe-submit-mcp`）触发上传。

### 教师需要向学生提供的信息

- 服务器地址（例如 `https://vibe.example.com`）。
- 课程 Marketplace 仓库 URL。
- 每位学生的 `submit_token`（在花名册 CSV 导入时由系统生成，明文可一次性导出）。

## 故障排查

| 现象 | 排查 |
|---|---|
| 容器无法启动 | 检查 `server/.env` 是否存在、`.env` 是否包含有效值；查看 `docker compose logs server`。 |
| 学生端提示无法连接 | 确认防火墙放行 8000 或反向代理端口；确认学生配置的 URL 协议为 HTTPS（生产环境）。 |
| 评估队列卡住 | 登录教师总览板查看失败任务；确认 `VIBE_LLM_API_KEY` 有效且余额充足；LLM 限流会触发自动退避重试。 |
| 忘记教师密码 | 目前无内置找回，可通过 `docker compose exec server vibe-server create-teacher <新用户名> <显示名>` 新建教师账号。 |

## 更新升级

```bash
git pull
docker compose up -d --build
```

如果数据结构发生变化，可进入容器执行必要的迁移（当前 MVP 使用 SQLAlchemy 自动建表，生产演进至 Alembic 后请按迁移文档操作）。
