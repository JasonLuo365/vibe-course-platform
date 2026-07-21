# 学生端网页说明

## 使用流程

1. 打开平台 `/login`，选择“学生登录”。
2. 输入教师发放的学号和 `submit_token`。
3. 登录后进入 `/student`，查看自己的课程、小组、作业和提交状态。
4. 对已经提交的作业，点击“查看详情”，进入 `/student/submissions/{submission_id}` 查看个人评语、小组评语、成绩和提交信息。

## 数据与权限

- 学生网页使用独立的 Session，不会改变插件使用的 Bearer token 鉴权。
- 学生只能读取 `student_id` 对应的提交；访问其他学生的提交编号会返回 404。
- 教师重置学生 token 时，学生网页会话版本同步失效，旧会话需要重新登录。
- 学生页面只读取当前学生所属课程和小组的作业与评估结果。

## 开发检查

在 `server` 目录执行：

```powershell
uv run pytest -q
```

当前学生端相关页面：

- `GET /login`：教师/学生角色选择登录页
- `POST /student/login`：学号 + `submit_token` 登录
- `GET /student`：学生作业首页
- `GET /student/submissions/{submission_id}`：学生评语详情页
- `POST /student/logout`：学生退出登录
