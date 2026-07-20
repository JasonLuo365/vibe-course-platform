# Vibe Coding 作业提交：教师操作与班级配置指南

生产地址：`https://vibe.planlabopc.com`。教师使用网页账户；学生不需要教师账户，也不应共享教师密码。

## 角色与分配规则

| 对象 | 需要的数据 | 谁创建/发放 | 注意事项 |
| --- | --- | --- |
| 学生 | 学号、姓名、小组、个人 `submit_token` | 导入名单后系统生成令牌；教师私发 | 每人一个令牌；数据库只保存哈希，明文只能在导入/重置时看到一次。 |
| 小组 | 课程内相同的小组名称 | CSV 导入自动生成 | 一名学生只属于一个课程内小组；可留空，系统归为“未分组”。 |
| 教师 | 用户名、显示名、初始密码 | VPS 管理员创建 | 当前教师账号可查看系统全部课程；只给真正需要阅卷的教师创建账号。 |
| 作业 | 标题、作业代码、开放/截止时间、量规、大小限制 | 教师创建 | 作业代码给全班相同；令牌绝不共享。 |

建议的顺序：**创建教师账号 → 创建课程 → 导入名单与分组 → 安全保存并私发令牌 → 创建作业 → 生成安装脚本 → 用测试学生完整验收**。

## 一、准备学生名单

使用 UTF-8 CSV。模板见 [`docs/roster-template.csv`](docs/roster-template.csv)：

```csv
学号,姓名,小组
20260001,张三,第1组
20260002,李四,第1组
20260003,王五,第2组
```

- 学号在同一课程内必须唯一；不要用 Excel 自动转换科学计数法后的学号。
- 相同“小组”文字自动归为同组；不分组时保留空白列。
- 先从教务系统导出名单，人工核对学号、姓名和分组，再导入。

## 二、创建教师、课程与学生令牌

SSH 到 VPS，进入项目目录：

```bash
cd ~/vibe-course-platform
```

创建教师账号（每名教师单独执行一次；密码不要出现在命令历史或截图中）：

```bash
read -s -p '教师初始密码: ' teacher_password; echo
sudo docker compose exec -e VIBE_TEACHER_PASSWORD="$teacher_password" server vibe-server create-teacher teacher02 "助教姓名"
unset teacher_password
```

创建课程并记下输出的课程 ID：

```bash
sudo docker compose exec server vibe-server create-course "课程名称" --term "2026 秋季"
```

将 `roster.csv` 上传到 VPS 后导入（把 `1` 换成课程 ID）：

```bash
sudo docker compose exec -T server vibe-server import-roster 1 < roster.csv > tokens.csv
chmod 600 tokens.csv
```

`tokens.csv` 包含 `学号,姓名,submit_token`。它是敏感文件：仅由课程负责人保存，并通过私信、学校账号或一对一邮件逐人发放。不要放在群聊、共享网盘链接、GitHub 或截图中。

如果个别学生遗失/泄露令牌，在网页 **学生管理 → 重置** 中生成新令牌；旧令牌会立即失效。

## 三、创建作业

准备 `assignment.json`（时间使用带时区的 ISO 格式）：

```json
{
  "title": "响应式网页设计",
  "description": "请完成指定页面并提交源代码、会话与截图。",
  "rubric": [
    {"name": "需求理解", "weight": 30, "description": "功能与任务匹配"},
    {"name": "实现质量", "weight": 40, "description": "代码结构、可运行性与界面"},
    {"name": "迭代能力", "weight": 30, "description": "根据反馈完善作品"}
  ],
  "opens_at": "2026-09-01T08:00:00+08:00",
  "deadline": "2026-09-07T23:59:00+08:00",
  "max_package_mb": 50
}
```

创建命令：

```bash
sudo docker compose exec -T server vibe-server create-assignment 1 --input assignment.json
```

记录输出的 `code`；它是全班共用的作业代码。不要在作业开放前发给学生。

## 四、生成并发放学生安装材料

在你的 Windows 项目根目录生成公共安装脚本（不含学生令牌）：

```powershell
.\ops\render-bootstrap.ps1 `
  -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' `
  -ServerUrl 'https://vibe.planlabopc.com' `
  -Version '0.1.2' `
  -OutputPath '.\release\bootstrap.ps1'
```

若班上有 macOS 学生，你仍可在同一台 Windows 电脑的 PowerShell 中生成对应脚本：

```powershell
.\ops\render-bootstrap.ps1 `
  -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' `
  -ServerUrl 'https://vibe.planlabopc.com' `
  -Version '0.1.2' `
  -OutputPath '.\release\bootstrap.sh' `
  -Platform macOS
```

全班公开发送：`STUDENT_GUIDE.md`、作业要求和作业代码；向 Windows 学生发 `release/bootstrap.ps1`，向 macOS 学生发 `release/bootstrap.sh`。逐人私发：学号确认信息与对应 `submit_token`。

## 五、教师网页使用

- **课程看板**：从“进入总览”查看每个学生的提交、队列与评估状态；“更多操作”可进入展示或下载反馈表。
- **学生管理**：检查名单、小组和状态，必要时重置单名学生令牌。
- **数据分析**：查看提交状态和 AI 等级分布；它仅用于教学汇总。
- **作业详情**：查看安全过滤后的会话、代码树、截图、AI 原评与教师调分。最终成绩应由教师审核决定。
- **反馈 Excel**：含“个人反馈”和“小组反馈”两页，便于阅卷、归档和后续导入成绩系统。

## 六、开课前与异常处理

1. 先用一个测试学生完成“安装 → 预览 → 上传 → 评估 → 教师查看 → Excel 导出”全链路。
2. 开课前访问 `https://vibe.planlabopc.com/health`，应返回 `status: ok` 且 `worker_enabled: true`。
3. 每次更新前先备份：`cd ~/vibe-course-platform && chmod +x ops/backup.sh && ./ops/backup.sh`。
4. 若 API Key、教师密码或令牌泄露：立即在对应服务更换密钥/密码，并重置受影响学生令牌。
5. 按学校隐私要求告知学生收集范围，限定只有授权教师可访问提交记录和导出表。
