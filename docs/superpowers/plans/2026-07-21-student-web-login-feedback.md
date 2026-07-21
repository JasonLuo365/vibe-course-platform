# 学生网页登录与评语门户实施计划（业务顺序版）

> **给智能代理执行者：** 执行本计划时必须使用 subagent-driven-development 或 executing-plans 子技能。每个任务都使用复选框跟踪进度，并在完成一个业务切片后运行对应测试。

**目标：** 按学生实际使用流程，增加教师/学生双入口登录、学生首页、提交详情和个人/小组评语页面。学生使用学号和 submit_token 登录，只能查看自己的数据。

**架构：** 继续使用现有 FastAPI + Jinja2 服务端渲染架构。复用现有 groups、students.group_id、submissions、submission_attempts、evaluations 和 group_evaluations 数据。第一版只修改 vibe-course-platform 仓库，不修改 vibe-course-marketplace，因为网页评语查看不依赖插件。

**技术栈：** Python 3.10+、FastAPI、SQLAlchemy 2.x、SQLite、Starlette SessionMiddleware、Jinja2、现有 CSS、pytest/TestClient、uv。

---

## 一、业务流程

系统最终按以下流程工作：

~~~text
教师创建课程并导入花名册/小组
        ↓
学生打开登录页，选择学生登录
        ↓
输入学号 + submit_token
        ↓
进入学生首页，看到课程、小组和作业状态
        ↓
打开自己的提交记录
        ↓
查看个人评语、小组评语、代码和截图
~~~

花名册导入和小组关系目前已经存在，本需求主要增加学生网页登录和学生查询页面。

## 二、范围与非目标

- 学生使用“学号 + submit_token”登录；本版本不增加学生密码、邮箱找回和短信验证。
- 教师登录、教师 Session、教师页面和教师 API 保持兼容。
- 学生只能查看自己的提交、个人评估和自己所属小组的小组评语。
- 第一版不修改 Codex 插件、MCP 工具、学生端 Python 包和 Marketplace 仓库。
- 不新增 Group 表，也不新增重复的 Submission 或 Evaluation 表。

## 三、仓库和文件边界

**修改仓库：** C:/Users/Lenovo/Desktop/vibe-course-platform-git

- server/app/templates/login.html：教师/学生角色选择和登录表单。
- server/app/templates/student_dashboard.html：学生首页。
- server/app/templates/student_feedback.html：提交详情和评语页面。
- server/app/templates/base.html：学生导航和页面外壳。
- server/app/static/app.css：登录、学生首页和评语页面样式。
- server/app/api/auth.py：学生登录和退出接口。
- server/app/deps.py：学生网页 Session 权限依赖。
- server/app/web/pages.py：学生页面路由。
- server/app/services/student_portal.py：学生门户查询数据。
- server/app/models.py：学生网页 Session 版本字段。
- server/app/db.py：已有 SQLite 数据库的结构升级。
- server/app/api/courses.py：重置 Token 时让旧网页 Session 失效。
- server/tests/test_student_web_portal.py：学生门户完整测试。
- STUDENT_GUIDE.md、TEACHER_GUIDE.md：登录和评语使用说明。

**暂不修改：**

C:/Users/Lenovo/Desktop/vibe-course-platform/vibe-course-marketplace

## 任务 1：先完成登录页面原型

这一阶段只做页面，不连接真实认证和数据库，先确认页面布局。

**文件：**

- 修改：server/app/templates/login.html
- 修改：server/app/static/app.css
- 测试：server/tests/test_student_web_portal.py

- [ ] **步骤 1：添加登录页面渲染测试。**

新增测试，断言 GET /login 返回 200，并包含：

- 教师登录文字和用户名/密码表单
- 学生登录文字和学号/Token 表单
- 教师登录接口 /login
- 学生登录接口 /student/login

- [ ] **步骤 2：运行失败测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py -q
~~~

预期：新增加的学生页面断言失败，原有教师登录测试不应被破坏。

- [ ] **步骤 3：增加教师/学生角色选择界面。**

教师登录默认选中。点击学生登录后显示：

- 学号输入框
- submit_token 输入框
- 登录按钮
- “Token 由教师私下发放，请勿分享”的说明

教师表单继续提交 username 和 password，不改变现有字段。

- [ ] **步骤 4：增加响应式样式。**

角色选择在桌面端显示为两个并排选项，在窄屏设备上垂直排列。使用真实 button 或 link，并提供键盘 focus 状态。

- [ ] **步骤 5：运行登录页面测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py tests/test_auth.py -q
~~~

- [ ] **步骤 6：提交登录页面原型。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add server/app/templates/login.html server/app/static/app.css server/tests/test_student_web_portal.py
git commit -m "feat: add teacher and student login choices"
~~~

## 任务 2：接通学生真实登录

这一阶段让学生可以使用学号和 submit_token 登录，但首页先只显示最小真实信息。

**文件：**

- 修改：server/app/api/auth.py
- 修改：server/app/deps.py
- 修改：server/app/models.py
- 修改：server/app/db.py
- 修改：server/app/api/courses.py
- 修改：server/app/web/pages.py
- 测试：server/tests/test_student_web_portal.py

- [ ] **步骤 1：先添加学生登录失败测试。**

准备两个同课程学生和不同 Token，测试：

- 正确学号 + Token 可以登录
- 错误 Token 登录失败
- 学号和 Token 不匹配时登录失败
- 学生 Session 不能进入教师页面
- 教师 Session 不能进入学生页面

- [ ] **步骤 2：增加学生网页 Session 版本字段。**

给 Student 增加 web_session_version，类型为整数、不可为空，默认值为 1。

- [ ] **步骤 3：增加已有 SQLite 数据库的升级逻辑。**

检查 students 表是否已有 web_session_version；没有时执行：

~~~sql
ALTER TABLE students
ADD COLUMN web_session_version INTEGER NOT NULL DEFAULT 1
~~~

升级逻辑必须幂等，应用重复启动时不能重复添加字段。

- [ ] **步骤 4：实现 POST /student/login。**

使用现有 hash_token 计算 Token 哈希，找到学生后校验学号，清理现有 Session，并写入：

~~~python
role = "student"
student_id = student.id
student_session_version = student.web_session_version
~~~

登录成功后跳转 /student。

- [ ] **步骤 5：实现学生网页认证依赖。**

增加 get_student_page，检查 role、student_id 和 web_session_version。未登录、角色错误、学生不存在或 Session 版本过期时跳转到学生登录页面。

不要用 Bearer Token 依赖替代网页 Session 依赖。

- [ ] **步骤 6：实现 POST /student/logout。**

清理当前 Session，跳转到 /login?role=student。

- [ ] **步骤 7：修改教师重置 Token 逻辑。**

重置 Token 时同时递增 web_session_version，让该学生已有的网页 Session 立即失效。

- [ ] **步骤 8：运行认证测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py tests/test_auth.py tests/test_student_auth.py -q
~~~

- [ ] **步骤 9：提交学生登录功能。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add server/app/api/auth.py server/app/deps.py server/app/models.py server/app/db.py server/app/api/courses.py server/app/web/pages.py server/tests/test_student_web_portal.py
git commit -m "feat: add student browser authentication"
~~~

## 任务 3：接通学生首页真实数据

这一阶段学生登录后可以看到自己的身份、课程、小组、作业和提交状态。

**文件：**

- 新建：server/app/services/student_portal.py
- 修改：server/app/web/pages.py
- 新建：server/app/templates/student_dashboard.html
- 修改：server/app/templates/base.html
- 修改：server/app/static/app.css
- 测试：server/tests/test_student_web_portal.py

- [ ] **步骤 1：添加首页查询测试。**

断言登录后的学生可以看到：

- 姓名和学号
- 课程
- 小组名称
- 作业名称和作业码
- 最新提交状态
- 评估状态

断言第二个学生不能看到第一个学生的记录。

- [ ] **步骤 2：创建学生门户查询服务。**

创建 dashboard_data(db, student)，返回学生身份、课程、小组、作业、最新提交状态和评估状态。查询必须以当前已认证学生的 student.id 为边界。

- [ ] **步骤 3：增加 GET /student。**

使用 get_student_page 保护路由，调用 dashboard_data，并渲染 student_dashboard.html。

- [ ] **步骤 4：制作学生首页。**

页面包含：

- 学生身份卡片
- 所属课程和小组
- 作业卡片
- 提交状态标签
- 评估状态标签
- 查看详情按钮
- 退出登录入口

没有小组时显示“未分组”，没有提交时显示“尚未提交”。

- [ ] **步骤 5：运行首页测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py tests/test_web_management.py -q
~~~

- [ ] **步骤 6：提交学生首页。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add server/app/services/student_portal.py server/app/web/pages.py server/app/templates/student_dashboard.html server/app/templates/base.html server/app/static/app.css server/tests/test_student_web_portal.py
git commit -m "feat: add student dashboard"
~~~

## 任务 4：接通提交详情和评语

这一阶段完成学生最核心的业务目标：查看自己的提交、个人评语和小组评语。

**文件：**

- 修改：server/app/services/student_portal.py
- 修改：server/app/web/pages.py
- 新建：server/app/templates/student_feedback.html
- 修改：server/app/static/app.css
- 测试：server/tests/test_student_web_portal.py

- [ ] **步骤 1：添加评语查询测试。**

测试以下情况：

- 学生可以看到自己的个人成绩和个人评语
- 学生可以看到自己小组的小组成绩和小组评语
- 学生看不到其他学生的个人评语
- 学生看不到其他小组的小组评语
- 没有评估时显示等待状态
- 评估失败时显示失败状态

- [ ] **步骤 2：创建提交评语查询函数。**

创建 submission_feedback(db, student, submission_id)，按以下链路查询：

~~~text
当前学生 → 当前学生的 Submission
          → SubmissionAttempt
          → Evaluation
          → 当前学生 group_id 对应的 GroupEvaluation
~~~

如果 submission_id 不属于当前学生，返回与提交不存在相同的结果。

- [ ] **步骤 3：增加 GET /student/submissions/{submission_id}。**

使用 get_student_page 保护路由，调用 submission_feedback，并渲染 student_feedback.html。

- [ ] **步骤 4：制作评语详情页面。**

页面显示：

- 作业名称和提交时间
- 提交状态
- 个人成绩
- 个人总体评语
- 各评分维度
- 反馈项目和改进建议
- 小组成绩
- 小组评语
- 代码和截图入口

评估排队、评估中和评估失败时显示明确的状态说明，不显示内部异常信息。

- [ ] **步骤 5：复用安全的代码和截图访问逻辑。**

复用教师提交详情页面中的压缩包解压路径和文件路径校验逻辑，禁止学生请求任意服务器文件路径。

- [ ] **步骤 6：运行评语页面测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py tests/test_web_detail.py tests/test_web_board.py tests/test_web_present.py -q
~~~

- [ ] **步骤 7：提交评语页面。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add server/app/services/student_portal.py server/app/web/pages.py server/app/templates/student_feedback.html server/app/static/app.css server/tests/test_student_web_portal.py
git commit -m "feat: add student feedback details"
~~~

## 任务 5：补齐权限、安全和异常场景

这一阶段不改变主业务流程，专门确保学生数据不会互相泄露。

**文件：**

- 修改：server/app/deps.py
- 修改：server/app/api/auth.py
- 修改：server/app/api/courses.py
- 修改：server/app/services/student_portal.py
- 修改：server/app/web/pages.py
- 测试：server/tests/test_student_web_portal.py

- [ ] **步骤 1：测试跨学生访问。**

学生 A 请求学生 B 的提交详情、评语和代码地址时，返回统一的 not-found 结果，不显示学生 B 的姓名、学号或提交状态。

- [ ] **步骤 2：测试跨小组访问。**

学生 A 只能看到自己所属小组的小组评估，不能通过修改 URL 读取其他小组的评语。

- [ ] **步骤 3：测试身份切换。**

学生退出后不能访问学生页面；教师登录后不能访问学生页面；学生不能访问教师 Dashboard、学生管理和分析页面。

- [ ] **步骤 4：测试 Token 重置。**

教师重置 Token 后，旧 Token 不能登录，旧学生网页 Session 也不能继续访问。

- [ ] **步骤 5：测试限流和错误提示。**

连续错误登录不能泄露“学号存在”或“Token 正确”等信息。页面只显示统一的登录失败消息。

- [ ] **步骤 6：运行完整安全测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest tests/test_student_web_portal.py tests/test_auth.py tests/test_student_auth.py tests/test_web_detail.py -q
~~~

- [ ] **步骤 7：提交安全修正。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add server/app/deps.py server/app/api/auth.py server/app/api/courses.py server/app/services/student_portal.py server/app/web/pages.py server/tests/test_student_web_portal.py
git commit -m "security: isolate student portal data"
~~~

## 任务 6：文档、完整测试和手工验收

**文件：**

- 修改：STUDENT_GUIDE.md
- 修改：TEACHER_GUIDE.md
- 必要时修改：README.md
- 测试：全部服务端测试

- [ ] **步骤 1：更新学生使用说明。**

说明学生如何打开登录页、选择学生登录、输入学号和 submit_token、查看提交和评语。明确 Token 不能提交到 Git 或分享。

- [ ] **步骤 2：更新教师操作说明。**

说明教师仍然通过花名册导入学生和小组，学生网页会读取现有小组关系。说明教师重置 Token 后旧网页登录会失效。

- [ ] **步骤 3：运行完整服务端测试。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git\server
uv run pytest -q
~~~

预期：原有测试和新增学生门户测试全部通过。

- [ ] **步骤 4：进行浏览器手工验收。**

使用测试 SQLite 数据库启动开发服务，完成以下流程：

1. 创建教师账号。
2. 创建课程。
3. 导入带小组字段的花名册。
4. 创建作业。
5. 用教师账号登录，确认教师页面正常。
6. 用学生 A 的学号和 Token 登录。
7. 确认学生首页显示课程、小组和提交状态。
8. 打开学生 A 的评语页面。
9. 确认学生 A 看不到学生 B 的提交。
10. 重置学生 A 的 Token，确认旧网页 Session 失效。

- [ ] **步骤 5：检查最终差异和仓库状态。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git diff --check
git status --short --branch
~~~

预期：没有空白字符错误，只有本功能相关文件发生变化，完成提交后工作区干净。

- [ ] **步骤 6：提交文档和验收更新。**

~~~powershell
cd C:\Users\Lenovo\Desktop\vibe-course-platform-git
git add README.md STUDENT_GUIDE.md TEACHER_GUIDE.md
git commit -m "docs: document student feedback portal"
~~~

## 四、发布和两个仓库的协作边界

- 第一版功能只在 vibe-course-platform 仓库的 ZM 分支实现。
- 浏览器查看学生评语不需要修改 vibe-course-marketplace。
- 如果以后需要让 Codex 插件直接打开评语，或者在插件内查询评语，应单独制定 Marketplace/客户端计划，同时更新版本号、插件元数据、MCP 工具契约和服务端 API。
- 部署前备份 SQLite 数据卷，并使用生产数据库副本验证结构升级逻辑。

## 五、执行前检查

- [ ] 已确认学生使用“学号 + submit_token”登录。
- [ ] 已确认第一版先做网页端，不修改 Marketplace。
- [ ] 已确认教师登录流程保持不变。
- [ ] 已确认学生只能查看自己的个人评估和自己小组的小组评估。
- [ ] 已确认按照业务顺序先完成登录原型，再接入真实数据。

