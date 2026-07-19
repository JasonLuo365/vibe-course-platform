# 课堂上线运行手册（一次受控上线）

## 课前一天

1. 在 Linux VPS 安装 Docker Compose 与 Caddy；将仓库放在仅管理员可读的目录。
2. 复制 `server/.env.example` 为 `server/.env`，填写域名、随机会话密钥、LLM Key；`VIBE_ALLOWED_HOSTS` 必须是包含实际域名、`localhost` 和 `127.0.0.1` 的 JSON 数组。
3. 复制 `Caddyfile.example` 为 VPS 上的 `Caddyfile`，把示例域名替换为真实域名；DNS A/AAAA 记录先指向 VPS。
4. 执行 `docker compose up -d --build`，再执行 `ops/preflight.sh`。
5. 创建教师账号：

   ```bash
   docker compose exec -e VIBE_TEACHER_PASSWORD='强密码' server \
     vibe-server create-teacher teacher1 '任课教师'
   ```

6. 从手机流量或校外网络访问 `https://真实域名/health` 与教师登录页。不得使用 HTTP 或自签名证书。

## 课前 30 分钟

1. 用 `vibe-server create-course`、`import-roster`、`create-assignment` 建立课堂数据，并保存一次性 token 表到受控位置；不要将 token 发送到群聊或投影屏幕。
2. 用两名真实/测试学生完成：安装、`doctor`、提交、教师看板、作品展示、评价展示、反馈 CSV 导出。
3. 运行 `ops/backup.sh`，确认生成 `.tar.gz` 与对应 `.sha256` 文件。
4. 查看 `docker compose logs --tail=100 server`，确认没有循环报错或 LLM 鉴权失败。

## 上课期间

1. 学生看到“提交成功”即可；AI 评价可能稍后完成，不要要求学生反复强制提交。
2. 首次提交按小组或按学号段分批进行，避免所有人同一分钟点击提交。
3. 无法上传时，先运行 `vibe-submit doctor`；网络问题使用 `vibe-submit retry`，不要重置 token。
4. 评测失败或排队时保留提交包，课后重试即可；教师端导出的反馈以评测完成后的版本为准。

## 课后

1. 再执行一次 `ops/backup.sh`，把两个备份复制到 VPS 之外的受控位置。
2. 导出反馈 CSV，核对文本建议后再发给学生。
3. 保存 `docker compose logs server` 与本次作业代码、rubric、LLM 模型名称，便于后续复核。

