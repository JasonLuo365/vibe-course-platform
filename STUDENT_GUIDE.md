# Vibe Coding 作业提交：学生使用指南

本指南适用于 Windows（PowerShell）或 macOS（终端）+ Codex。教师只需在课程群或课程平台发布：

- 作业代码；
- 课程邀请码。

首次安装时填写课程邀请码、学号、姓名，并设置两次相同的个人密码。请妥善保管密码，不要发到 Codex 对话中。

## 第一次安装：Windows 10/11

打开 **Windows PowerShell**，直接复制并运行以下命令：

```powershell
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
$source = "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.6#subdirectory=packages/vibe-submit"
uvx --from $source vibe-submit bootstrap `
  --marketplace-url "https://github.com/JasonLuo365/vibe-course-marketplace.git" `
  --marketplace-name "vibe-course" `
  --server "https://vibe.planlabopc.com"
```

按提示输入课程邀请码、学号、姓名、密码和确认密码；服务器地址已固定，无需修改。看到 `doctor` 中的 `Server reachable` 后，在终端运行 `codex plugin add vibe-submit@vibe-course` 安装插件，然后完全退出并重新打开 Codex。若提示找不到 `codex` 或安装失败，则在重启后的“插件 / Marketplace”中找到 **Vibe Course**，安装 **Vibe 作业提交**。

> 如果 PowerShell 显示“无法识别 uv/uvx”，关闭当前 PowerShell，再新建一个 PowerShell 窗口重试。

## 第一次安装：macOS

打开 **终端**（Terminal），直接复制并运行以下命令：

```bash
if ! command -v uvx >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
source="git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.6#subdirectory=packages/vibe-submit"
uvx --from "$source" vibe-submit bootstrap \
  --marketplace-url "https://github.com/JasonLuo365/vibe-course-marketplace.git" \
  --marketplace-name "vibe-course" \
  --server "https://vibe.planlabopc.com"
```

按提示输入课程邀请码、学号、姓名、密码和确认密码；服务器地址已固定，无需修改。看到 `doctor` 中的 `Server reachable` 后，在终端运行 `codex plugin add vibe-submit@vibe-course` 安装插件，然后完全退出并重新打开 Codex。若提示找不到 `codex` 或安装失败，则在重启后的“插件 / Marketplace”中找到 **Vibe Course**，安装 **Vibe 作业提交**。若终端提示找不到 `uv`/`uvx`，关闭终端后重新打开，再运行一次上述完整命令。

## 首次组队

在 Codex 对话中说“查看我的小组”。未分组时可以说“创建小组”，填写显示组名后会得到 6 位组队码；把它发给组员。组员说“加入小组”并输入组队码即可。教师锁定分组后，需由教师调整成员。

创建小组时可以自己填写组名；创建完成后不能自行改名或换组。如需更正，请联系教师在“学生管理”中处理。

## 日常作业流程

1. 使用 Codex 在**同一个作业项目文件夹**中完成作业。会话记录必须产生在该项目下。
2. 在项目根目录创建 `report` 文件夹，并把**最终作业报告**放入其中。建议使用 `final-report.md`（也可使用 `txt`、`csv` 或 `html`）；它会与代码、截图和 Codex 会话记录一起提交，并在教师端的“报告”页签单独展示。再如需提交截图，在项目根目录创建 `screenshots` 文件夹，把 `png`、`jpg`、`jpeg`、`gif`、`webp` 或 `bmp` 图片放进去，例如：

   ```text
   我的作业/
   ├─ snake.html
   ├─ tests/
   ├─ report/
   │  └─ final-report.md
   └─ screenshots/
      └─ 首页.png
   ```

3. 在 Codex 对话中说“预览 Vibe 作业并展示内容”。插件会先列出将上传的代码树、最终报告、截图、会话；你可以继续要求“打开 `code/xxx`”“打开 `report/final-report.md`”或“展开某个会话”。会话预览只显示你的提示词和 Codex 最终回答，不显示思考过程、工具输出或内部指令。
4. 确认内容无误后明确说“确认提交”。也可以在项目根目录手动执行：

   ```powershell
   vibe-submit submit --code <老师提供的作业代码> --project .
   ```

5. 工具会显示待上传文件数量和大小，输入 `y` 后才真正上传。看到 `Submitted successfully` 即表示服务器已收到；AI 评估需要稍等，教师端会显示最终状态。

## 查看评估反馈

教师发布后，在 Codex 对话中说“查看我的评估反馈”；若只查看某次作业，可说“查看作业 `<作业代码>` 的评估反馈”。插件会显示个人报告，以及你所在小组的已发布小组报告。个人报告包含最终等级、各评分维度、综合说明和可执行的改进建议；小组报告只包含团队共同的等级、总结和教师备注，不会显示其他成员的个人评价。

报告保存在课程服务器中，不会自动放进作业文件夹：这样能保护你的个人反馈，也不会让反馈文件被下次作业误提交。每次查看时都会取得教师已发布的最新版本；若教师调分或补充备注，以最新显示为准。

也可以在终端执行：

```powershell
vibe-submit report --code <作业代码>
```

省略 `--code` 可查看所有作业的报告状态。若显示“评估中”或“等待教师发布”，代表结果尚未对学生开放；系统不会提前显示草稿分数。

如需自己留存一份副本，可在**作业文件夹之外**建立文件夹后导出。例如 Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\Vibe反馈" | Out-Null
vibe-submit report --code <作业代码> | Out-File -Encoding utf8 "$env:USERPROFILE\Documents\Vibe反馈\<作业代码>-反馈.json"
```

这是可选的个人备份，文件只保存在你的电脑上；不要把它放进作业项目或 `screenshots` 文件夹，也不要转发给无关人员。

## 网络失败与重试

上传失败时，提交包会安全保留在本机 outbox。网络恢复后在项目根目录执行：

```powershell
vibe-submit retry
```

不要重复生成不同作业文件后盲目重试；先运行预览，确认重试的是正确版本。

## 常见问题

**插件只显示“预览成功，未提交”的摘要，没法看内容？** 让 Codex 继续调用“查看预览内容”；若仍无内容，退出并重新打开 Codex，再重新安装老师提供的最新插件版本。预览 ID 约一小时后会过期，过期后重新预览即可。

**显示没有 Codex 会话？** 请确认：在作业项目文件夹内启动/使用了 Codex；作业会话发生在作业开放时间后；提交时 `--project` 指向该项目根目录。

**提示证书、服务器不可达或域名解析到 `198.18.x.x`？** 先关闭 VPN 的 TUN/Fake-IP 模式，或切换到正常网络后运行：

```powershell
vibe-submit doctor
```

**文件过大？** 单个文件不能超过 10 MB，整个作业包受教师设置的总大小限制。删除构建产物、依赖目录、密钥和大文件后再预览。

**忘记密码？** 打开平台登录页，选择“学生登录”并点击“忘记密码？”。输入学号后设置并确认新密码。

**macOS 提示找不到 `uvx`？** 关闭终端后重新打开，再运行一次上述完整命令。

## 隐私与提交范围

上传包只收集项目代码、`report/` 中的最终报告、`screenshots/` 中的截图及匹配该项目的 Codex 会话。不要把 `.env`、API Key、密码、个人资料或其他课程文件放进作业目录。提交前始终先预览。
