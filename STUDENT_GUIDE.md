# Vibe Coding 作业提交：学生使用指南

本指南适用于使用 Codex 完成课程项目的学生。开始前，请向教师获取：**课程邀请码**和每份作业的**作业代码**。安装与注册时还需要使用自己的学号、姓名和密码。

## 一、你需要完成的事情

1. 在自己的电脑上安装 Vibe 作业提交插件并登记课程。
2. 如课程要求分组，创建或加入小组。
3. 在同一个项目文件夹内使用 Codex 完成作业。
4. 先预览，再明确确认提交。
5. 等教师发布后，查看自己的评估反馈。

请勿把密码、邀请码、API Key 或个人反馈发到聊天群或 Codex 对话中。

## 二、首次安装与课程登记

安装只需做一次；更换电脑时需要重新执行。安装过程会依次要求输入：课程邀请码、学号、姓名、用户密码和确认密码。密码长度应为 8–128 个字符，两次输入必须一致。

### Windows 10/11（PowerShell）

打开 **Windows PowerShell**，完整复制运行：

```powershell
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
$source = "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.7#subdirectory=packages/vibe-submit"
uvx --from $source vibe-submit bootstrap `
  --marketplace-url "https://github.com/JasonLuo365/vibe-course-marketplace.git" `
  --marketplace-name "vibe-course" `
  --server "https://vibe.planlabopc.com"
```

看到 `doctor` 中的 `Server reachable` 后，完全退出并重新打开 Codex。若终端可使用 `codex` 命令，可运行：

```powershell
codex plugin add vibe-submit@vibe-course
```

若没有该命令或命令报错，重启 Codex 后在“插件 / Marketplace”中找到 **Vibe Course**，安装 **Vibe 作业提交**。

### macOS（终端）

打开 **终端**，完整复制运行：

```bash
if ! command -v uvx >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
source="git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.7#subdirectory=packages/vibe-submit"
uvx --from "$source" vibe-submit bootstrap \
  --marketplace-url "https://github.com/JasonLuo365/vibe-course-marketplace.git" \
  --marketplace-name "vibe-course" \
  --server "https://vibe.planlabopc.com"
```

随后重启 Codex 并安装 **Vibe Course → Vibe 作业提交**。若提示找不到 `uvx`，关闭终端后重新打开，再运行一次完整命令。

### 登记失败时先检查

- 邀请码必须属于本课程，且仍为教师当前发放的版本。
- 如果教师已用 CSV 导入名单，学号和姓名必须与名单完全一致。
- 若提示已登记，请不要反复注册，改用“忘记密码”设置新密码。
- 可运行 `vibe-submit doctor` 检查服务器连通性。

## 三、组队

在 Codex 中说“查看我的小组”。未分组时可以：

- 说“创建小组”，输入小组显示名称，系统会返回 6 位组队码；把它私下发给组员。
- 组员说“加入小组”，再输入该组队码。

创建后不能自行换组或改名。教师锁定分组后，学生也不能再创建或加入小组；请联系教师在“学生管理”中调整。请在首次提交前完成组队确认。

## 四、完成作业并预览

请在**同一个作业项目文件夹**中使用 Codex，提交时也以这个文件夹为项目根目录。系统会收集：项目代码、`report/` 内的最终报告、`screenshots/` 内的截图，以及与该项目匹配的 Codex 会话。

建议目录如下：

```text
我的作业/
├─ src/
├─ README.md
├─ report/
│  └─ final-report.md
└─ screenshots/
   └─ 首页.png
```

- `report/` 是可选的最终报告目录；推荐 `final-report.md`，也可使用 TXT、CSV 或 HTML。
- `screenshots/` 是可选截图目录，支持 PNG、JPG、JPEG、GIF、WEBP、BMP。
- 不要把 `.env`、密码、API Key、依赖目录或无关个人文件放入项目目录。

在 Codex 对话中说“预览 Vibe 作业并展示内容”，并提供教师给出的作业代码。插件会列出代码树、报告、截图、会话和被排除的文件；你可继续要求打开某个代码文件、报告或会话。会话预览只显示你的提示词与 Codex 最终回答，不会提交思考过程或工具输出。

## 五、确认提交与查看状态

预览无误后，明确说“确认提交”。插件会再次要求确认，只有确认后才上传。

也可在项目根目录执行：

```powershell
vibe-submit submit --code <教师提供的作业代码> --project .
```

看到 `Submitted successfully` 即表示服务器已收到提交。若上传失败，提交包会保存在本机 outbox；恢复网络后运行：

```powershell
vibe-submit retry
```

重试前先确认项目内容与作业代码正确，不要因为网络失败而随意重复提交不同版本。

## 六、网页查看反馈

AI 评估完成后，仍需等待教师发布。发布前，系统不会显示草稿分数。

请打开学生登录页：<https://vibe.planlabopc.com/login>

选择“学生登录”，输入学号和密码。登录后可查看自己的课程、提交状态和已发布的个人/小组反馈。

个人反馈只对本人可见；小组反馈只显示本组共同结果和教师备注，不会显示其他同学的个人评价。若希望保存反馈副本，请导出到作业文件夹之外的位置，避免在下次提交时误上传。

### 忘记密码

在平台登录页选择“学生登录”，点击“忘记密码？”。输入学号，设置并确认新密码后，再使用新密码登录或重新运行安装命令。请注意：该课程目前按学号重置密码，务必妥善保护自己的学号信息。

## 七、常见问题

**没有找到 Codex 会话？** 确认会话是在作业项目文件夹内进行，且 `--project` 指向该项目根目录。

**服务器不可达、证书错误或域名解析异常？** 关闭 VPN 的 TUN/Fake-IP 模式，切换到正常网络后运行 `vibe-submit doctor`。

**文件过大？** 单个文件不能超过 10 MB；整个提交包还受教师设置的大小上限约束。删除构建产物、依赖和大文件后重新预览。

**插件没有出现？** 完全退出并重启 Codex；仍无效时在 Marketplace 手动安装 **Vibe Course** 中的 **Vibe 作业提交**。
