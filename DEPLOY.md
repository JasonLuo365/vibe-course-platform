# 受控课堂上线部署指南

本指南用于一次 100 人以内的课堂。当前架构是单个 Web 进程加内嵌评测 worker：请保持单实例、单 worker，不要使用 `uvicorn --workers`。

## 上线前准备

- 一台 Linux VPS、一个已解析到该 VPS 的域名、开放 80/443 端口。
- Docker Engine、Docker Compose plugin、Caddy。
- 可用且有额度的 OpenAI 兼容 LLM API Key。
- 已发布且固定版本的 `vibe-submit`；发布后先在一台干净 Windows 机器上验证安装与提交。

## 部署

```bash
git clone <你的仓库地址> vibe-classroom
cd vibe-classroom
cp server/.env.example server/.env
chmod 600 server/.env
```

编辑 `server/.env`：

- `VIBE_SESSION_SECRET` 必须是至少 32 个字符的随机值；可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成。
- `VIBE_ALLOWED_HOSTS` 中替换真实域名，并保留 `localhost`、`127.0.0.1`。
- 填写 LLM 地址、模型名和 API Key。
- 保持 `VIBE_ENVIRONMENT=production`、`VIBE_SESSION_HTTPS_ONLY=true`、`VIBE_TRUST_PROXY_HEADERS=true`。

应用端口只绑定在 `127.0.0.1:8000`，不会直接暴露 HTTP：

```bash
docker compose up -d --build
```

复制 `Caddyfile.example` 到 Caddy 的配置目录，替换域名后加载：

```bash
sudo cp Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 会自动申请并续期证书。DNS 生效后，必须从 VPS 之外访问 `https://你的域名/health`，确认返回 `status: ok`。

## 教师账号与课堂数据

```bash
docker compose exec -e VIBE_TEACHER_PASSWORD='强密码' server \
  vibe-server create-teacher teacher1 '任课教师'
```

用以下命令建立课程、导入花名册和作业。课程在登录教师之间共享；学生 token 仅在导入时明文导出一次，必须单独、私密地发送给学生。

```bash
# 返回的 id 作为下方 <course-id> 使用
docker compose exec server vibe-server create-course 'Vibe Coding' --term '2026 夏'

# 保存输出的 token 表；绝不要提交到 Git 或发送到群聊。
docker compose exec -T server vibe-server import-roster <course-id> --input - \
  < ops/roster.csv > student-tokens.csv

# 修改 ops/assignment.json 后创建作业；命令输出作业 code。
docker compose exec -T server vibe-server create-assignment <course-id> --input - \
  < ops/assignment.json
```

可从 `ops/roster.example.csv` 和 `ops/assignment.example.json` 复制出本次课堂文件。创建完成后可登录教师端查看共享课程与作业。

## 课前检查

```bash
chmod +x ops/*.sh
ops/preflight.sh
ops/backup.sh
docker compose logs --tail=100 server
```

还必须完成两名测试学生的端到端演练：安装、`doctor`、提交、教师看板、作品展示、评价展示和反馈 CSV 导出。

学生客户端发布和生成课堂安装脚本的步骤见 [client/RELEASE.md](client/RELEASE.md)。

## 备份与恢复

`ops/backup.sh` 会在 `backups/` 创建包含 SQLite 数据库和所有提交文件的压缩包及 SHA-256 文件。课前、课后各执行一次，并把至少一个副本复制到 VPS 外部。

恢复脚本具有破坏性，只有在确认需要恢复时执行：

```bash
ops/restore.sh --confirm /绝对路径/vibe-data-YYYYMMDD-HHMMSSZ.tar.gz
```

脚本会要求再次输入 `RESTORE`，并在完成后重启服务。恢复后先运行 `ops/preflight.sh`，再登录验证数据。

## 课堂期间

- 以“提交已收到”为成功标准；AI 评价可以稍后完成。
- 让学生按学号段或小组分批首次提交；网络错误使用 `vibe-submit retry`。
- 不要在课堂中切换版本、修改 rubric、重启服务或强制重新提交。
- 出现故障先保存 `docker compose logs server`，再做修复；不要删除 `data` 卷。

完整的教师操作清单见 [ops/classroom-runbook.md](ops/classroom-runbook.md)。

