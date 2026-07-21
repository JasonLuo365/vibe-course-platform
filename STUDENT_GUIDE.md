# Vibe Coding 作业提交：学生使用指南

本指南适用于 Windows（PowerShell）或 macOS（终端）+ Codex。教师会在课程群或课程平台统一发布：

- 课程安装脚本：Windows 为 `bootstrap.ps1`，macOS 为 `bootstrap.sh`；
- 作业代码（通常在作业开放时发布）；
- 课程邀请码；

安装时系统会用“课程邀请码 + 学号 + 姓名”自动为你注册，并将个人提交凭证安全保存在你的电脑中。不要尝试查看、截图、转发或写入 Git 仓库。

## 让 Codex 协助安装（推荐）

你可以让 Codex 阅读本指南并协助完成安装，不需要理解 `uv`、Marketplace 或命令行的细节。先将老师发来的 `bootstrap.ps1`（macOS 为 `bootstrap.sh`）保存到本机，再把**脚本文件和本指南**拖入一个新的 Codex 对话，发送下面这段话：

```text
请按 STUDENT_GUIDE.md 协助我安装 Vibe 作业提交插件。安装脚本是老师发来的 bootstrap 文件；请先检查脚本中没有 TODO 占位符，再引导我运行它。注册时我会在本机终端输入学号、姓名和老师公布的课程邀请码；不要要求我在对话中提供或展示任何 submit_token。安装检查成功后，如本机有 codex 命令，请运行 `codex plugin add vibe-submit@vibe-course` 安装插件；否则指导我重启 Codex，并在 Vibe Course Marketplace 中安装“Vibe 作业提交”插件。
```

Codex 可能会请求你批准安装 `uv` 或运行脚本；仅在确认脚本来自老师、服务器地址正确时批准。安装程序会自动生成并保存你的提交凭证；不要要求 Codex 展示它，也不要将其粘贴到对话、截图或作业文件中。

## 第一次安装：Windows 10/11

1. 保存老师发来的 `bootstrap.ps1`，例如保存到“下载”文件夹。
2. 打开 **Windows PowerShell**，进入脚本所在文件夹：

   ```powershell
   cd "$env:USERPROFILE\Downloads"
   Set-ExecutionPolicy -Scope Process Bypass
   .\bootstrap.ps1
   ```

3. 第一次执行时会自动安装 `uv`（Python 工具）并登记课程 Marketplace。服务器地址已由老师写入脚本；按提示输入你的**学号、姓名和课程邀请码**，且不要修改服务器地址。系统会自动完成注册并在本机保存提交凭证。
4. 看到 `doctor` 中的 `Server reachable` 后，可以在终端执行 `codex plugin add vibe-submit@vibe-course` 直接安装插件；成功后完全退出并重新打开 Codex。若提示找不到 `codex` 或安装失败，则在重启后的“插件 / Marketplace”中找到 **Vibe Course**，安装 **Vibe 作业提交**。这一步完成后才可以在 Codex 对话中使用提交功能。

> 如果 PowerShell 显示“无法识别 uv/uvx”，关闭当前 PowerShell，再新建一个 PowerShell 窗口重试。

## 第一次安装：macOS

1. 保存老师发来的 `bootstrap.sh` 到“下载”文件夹。只运行教师直接发放的脚本。
2. 打开 **终端**（Terminal），执行：

   ```bash
   cd ~/Downloads
   bash ./bootstrap.sh
   ```

3. 脚本会在你的用户目录安装 `uv`，不需要管理员密码。服务器地址已由老师写入脚本；按提示输入你的**学号、姓名和课程邀请码**，且不要修改服务器地址。系统会自动完成注册并在本机保存提交凭证。
4. 看到 `doctor` 中的 `Server reachable` 后，可以在终端执行 `codex plugin add vibe-submit@vibe-course` 直接安装插件；成功后完全退出并重新打开 Codex。若提示找不到 `codex` 或安装失败，则在重启后的“插件 / Marketplace”中找到 **Vibe Course**，安装 **Vibe 作业提交**。若终端提示找不到 `uv`/`uvx`，关闭终端后重新打开，再运行一次 `bash ./bootstrap.sh`。

## 日常作业流程

1. 使用 Codex 在**同一个作业项目文件夹**中完成作业。会话记录必须产生在该项目下。
2. 如需提交截图，在项目根目录创建 `screenshots` 文件夹，把 `png`、`jpg`、`jpeg`、`gif`、`webp` 或 `bmp` 图片放进去，例如：

   ```text
   我的作业/
   ├─ snake.html
   ├─ tests/
   └─ screenshots/
      └─ 首页.png
   ```

3. 在 Codex 对话中说“预览 Vibe 作业并展示内容”。插件会先列出将上传的代码树、截图、会话；你可以继续要求“打开 `code/xxx`”或“展开某个会话”。会话预览只显示你的提示词和 Codex 最终回答，不显示思考过程、工具输出或内部指令。
4. 确认内容无误后明确说“确认提交”。也可以在项目根目录手动执行：

   ```powershell
   vibe-submit submit --code <老师提供的作业代码> --project .
   ```

5. 工具会显示待上传文件数量和大小，输入 `y` 后才真正上传。看到 `Submitted successfully` 即表示服务器已收到；AI 评估需要稍等，教师端会显示最终状态。

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

**换电脑、清除了本机配置或注册提示“学号已登记”？** 不要借用同学的电脑或凭证。联系教师在“学生管理”中重置你的提交凭证，并按教师给出的恢复步骤操作；旧凭证会立刻失效。

**macOS 显示“permission denied”或无法运行？** 在终端使用 `bash ./bootstrap.sh`，不要双击脚本；确认脚本来自教师后再运行。

## 隐私与提交范围

上传包只收集项目代码、`screenshots/` 中的截图及匹配该项目的 Codex 会话。不要把 `.env`、API Key、密码、个人资料或其他课程文件放进作业目录。提交前始终先预览。
