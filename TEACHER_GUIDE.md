# Vibe Coding 作业提交：教师操作手册

生产地址：`https://vibe.planlabopc.com`。教师用自己的账号登录网页；学生不用网页登录，也不共享教师密码。

## 一、准备名单与分组

准备 UTF-8 CSV 文件，第一行固定为：

```csv
学号,姓名,小组
20260001,张三,第1组
20260002,李四,第1组
20260003,王五,第2组
```

- `小组` 可留空；系统会将相同的小组名自动归为同一组。
- 每名学生必须有唯一学号。
- 导入后系统生成一人一个 `submit_token`，数据库只保存令牌哈希，**不会再次显示原令牌**。请把导出的令牌表保存到受保护的位置，并逐一私密发放。

目前名单导入与课程/作业创建使用服务器命令行。先 SSH 到 VPS，进入项目目录：

```bash
cd ~/vibe-course-platform
sudo docker compose exec server vibe-server create-course "课程名称" --term "2026 秋季"
sudo docker compose exec -T server vibe-server import-roster 1 < roster.csv > tokens.csv
chmod 600 tokens.csv
```

将上面的 `1` 替换成实际课程 ID。接着按项目中的 CLI 帮助创建作业：

```bash
sudo docker compose exec server vibe-server --help
sudo docker compose exec server vibe-server create-assignment --help
```

作业必须设置开放时间、截止时间、评分量规和包大小上限。创建完成后，把作业代码、学生安装脚本和各自令牌发送给学生。

## 二、生成并发放学生安装脚本

在教师自己的 Windows 项目目录中执行：

```powershell
.\ops\render-bootstrap.ps1 `
  -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' `
  -ServerUrl 'https://vibe.planlabopc.com' `
  -Version '0.1.5' `
  -OutputPath '.\release\bootstrap.ps1'
```

若班上有 macOS 学生，你仍可在同一台 Windows 电脑的 PowerShell 中生成对应脚本：

```powershell
.\ops\render-bootstrap.ps1 `
  -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' `
  -ServerUrl 'https://vibe.planlabopc.com' `
  -Version '0.1.5' `
  -OutputPath '.\release\bootstrap.sh' `
  -Platform macOS
```

把 `release/bootstrap.ps1`（Windows）或 `release/bootstrap.sh`（macOS）和 `STUDENT_GUIDE.md` 发给对应学生；令牌只单独私发。脚本不应包含任何学生令牌。

## 三、网页端日常操作

- **课程看板**：进入某门作业，查看分组与每名学生的提交/评估进度。
- **作业详情**：查看 AI 原评、教师调分、会话记录、代码树和截图。会话记录按 Codex 会话分组，只显示有效的学生提示词和对应最终回答。
- **学生管理**：查看名单、小组与提交状态。点击“重置”会生成一次性可见的新令牌；复制后通过私密渠道给学生。旧令牌立即失效。
- **数据分析**：查看课程范围内的提交状态和 AI 等级分布。它是教学汇总，不应用作唯一的评分依据。

## 四、发布前与课堂中检查

1. 用一个测试学生在干净 Windows 账户按学生指南安装一次。
2. 完整测试“预览内容 → 确认提交 → AI 评估 → 网页查看代码/截图/会话”。
3. 在作业开放前检查：`https://vibe.planlabopc.com/health` 返回 `status: ok` 且 `worker_enabled: true`。
4. 令牌、API Key、教师密码绝不写入 Git 仓库、聊天记录或 CSV 截图。
5. AI 评估异常时，教师可以在详情页保留 AI 原评并用“教师调分”给出最终等级和备注。

## 五、更新、备份与恢复

每次更新前在 VPS 执行备份：

```bash
cd ~/vibe-course-platform
chmod +x ops/backup.sh
./ops/backup.sh
```

更新私有平台仓库并重建服务：

```bash
cd ~/vibe-course-platform
GIT_SSH_COMMAND='ssh -i ~/.ssh/vibe_course_platform -o IdentitiesOnly=yes' git pull --ff-only
sudo docker compose up -d --build
sudo docker compose ps
curl -fsS https://vibe.planlabopc.com/health
```

备份文件位于 `~/vibe-course-platform/backups/`；复制一份到另一个受保护的位置。若 API Key 或任一令牌泄露，应立即在对应服务中撤销/更换，然后在“学生管理”重置受影响学生的令牌。

## 六、交付前责任边界

系统已覆盖提交、队列、评估写回、教师展示、名单分组、令牌重置与基础统计。仍需由课程负责人执行最终人工验收：确认评分量规合理、抽查 AI 评估、妥善保管学生信息和备份，并依据学校要求处理隐私告知与成绩复核。
