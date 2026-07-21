# Vibe Coding 作业提交：教师操作手册

生产地址：`https://vibe.planlabopc.com`。教师用自己的账号登录网页；学生不用网页登录，也不共享教师密码。

## 一、创建课程与开放学生自助注册

当前流程不需要预先导入花名册，也不需要给学生预先生成 `submit_token`。先创建课程和作业：

```bash
cd ~/vibe-course-platform
sudo docker compose exec server vibe-server create-course "课程名称" --term "2026 秋季"
```

接着按项目中的 CLI 帮助创建作业：

```bash
sudo docker compose exec server vibe-server --help
sudo docker compose exec server vibe-server create-assignment --help
```

作业必须设置开放时间、截止时间、评分量规和包大小上限。随后在网页“学生管理”中为该课程点击“生成/重置邀请码”，设置每组最大人数；把邀请码发到课程群。学生安装插件时自行填写学号、姓名和邀请码，服务器自动创建其身份与提交凭证。

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

将 `release/bootstrap.ps1`（Windows）、`release/bootstrap.sh`（macOS）和 `STUDENT_GUIDE.md` 统一发布到课程群或课程平台；再公布课程邀请码。所有学生共用同一份脚本，脚本不包含邀请码或任何学生凭证。

## 三、网页端日常操作

- **课程看板**：进入某门作业，查看分组与每名学生的提交/评估进度。
- **作业详情**：查看 AI 原评、教师调分、会话记录、代码树和截图。会话记录按 Codex 会话分组，只显示有效的学生提示词和对应最终回答。
- **学生管理**：生成或重置课程邀请码、设置每组最大人数、锁定分组，并查看学生、小组与提交状态。仅当学生换电脑或本机凭证丢失时，才需要重置该学生的提交凭证；旧凭证立即失效。
- **数据分析**：查看课程范围内的提交状态和 AI 等级分布。它是教学汇总，不应用作唯一的评分依据。

## 四、发布前与课堂中检查

1. 用一个测试学生在干净 Windows 账户按学生指南安装一次。
2. 完整测试“预览内容 → 确认提交 → AI 评估 → 网页查看代码/截图/会话”。
3. 在作业开放前检查：`https://vibe.planlabopc.com/health` 返回 `status: ok` 且 `worker_enabled: true`。
4. 学生提交凭证、API Key、教师密码绝不写入 Git 仓库、聊天记录或截图。课程邀请码仅用于注册，应只在本课程范围内公布；如误发或泄露，可在“学生管理”中重置。
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

备份文件位于 `~/vibe-course-platform/backups/`；复制一份到另一个受保护的位置。若 API Key 泄露，应立即在对应服务中撤销/更换；课程邀请码泄露则在“学生管理”重新生成。

## 六、交付前责任边界

系统已覆盖提交、队列、评估写回、教师展示、名单分组、令牌重置与基础统计。仍需由课程负责人执行最终人工验收：确认评分量规合理、抽查 AI 评估、妥善保管学生信息和备份，并依据学校要求处理隐私告知与成绩复核。
