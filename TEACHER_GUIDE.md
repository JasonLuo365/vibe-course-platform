# 教师指南

生产地址为 `https://vibe.planlabopc.com`。教师登录网页；学生不共享教师账号。

## 名单、分组与令牌

准备 UTF-8 CSV：

```csv
学号,姓名,小组
20260001,张三,第1组
20260002,李四,第1组
```

相同小组名会自动分组。导入会生成一人一个令牌，数据库只存哈希；导出的明文令牌只能通过私密渠道逐人发放。

SSH 到 VPS 后执行：

```bash
cd ~/vibe-course-platform
sudo docker compose exec server vibe-server create-course "课程名称" --term "2026 秋季"
sudo docker compose exec -T server vibe-server import-roster 1 < roster.csv > tokens.csv
chmod 600 tokens.csv
```

用 `sudo docker compose exec server vibe-server create-assignment --help` 查看创建作业参数；作业需设置开放/截止时间、量规和包大小。

## 给学生发什么

在项目根目录生成不含令牌的安装脚本：

```powershell
.\ops\render-bootstrap.ps1 -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' -ServerUrl 'https://vibe.planlabopc.com' -Version '0.1.2' -OutputPath '.\release\bootstrap.ps1'
```

公开发送该脚本和 `STUDENT_GUIDE.md`；令牌只私发。

## 网页端与维护

- 课程看板：按作业查看提交/评估进度。
- 学生管理：查看名单、分组和状态；“重置”显示一次新令牌，旧令牌随即失效。
- 数据分析：显示提交状态及 AI 等级汇总。
- 作业详情：查看会话、代码、截图、AI 原评并进行教师调分。

每次更新前备份：`cd ~/vibe-course-platform && chmod +x ops/backup.sh && ./ops/backup.sh`。更新后使用部署密钥执行 `git pull --ff-only`，再运行 `sudo docker compose up -d --build`，并访问 `/health` 验收。AI 评估必须人工抽查；不要将 API Key、教师密码或学生令牌写入仓库或聊天记录。
