# Vibe Coding 作业提交：学生安装与使用指南

适用环境：Windows 10/11（PowerShell）或 macOS（终端），以及 Codex。请将此文件保存在作业项目中；需要协助时可把它拖入 Codex 对话，并说“请严格按这份 Vibe 作业指南协助我预览和提交，不要索取或展示我的令牌”。

## 你会收到什么

教师会发送四项信息：

1. Windows 使用 `bootstrap.ps1`，macOS 使用 `bootstrap.sh`（均为全班相同的安装脚本）；
2. 作业代码，例如 `AB12CD34`；
3. 你的学号；
4. 你的个人 `submit_token`，形如 `vs_...`（仅私发给你）。

`submit_token` 相当于提交密码：不能发给同学、不能粘贴到 Codex 对话、不能提交到 Git，也不要放进截图。忘记或泄露后只能请教师重置。

## 第一次安装

### Windows 10/11

1. 把教师提供的 `bootstrap.ps1` 保存到下载文件夹。
2. 打开 **Windows PowerShell**，不要在 CMD 中执行。进入脚本目录：

   ```powershell
   cd "$env:USERPROFILE\Downloads"
   Set-ExecutionPolicy -Scope Process Bypass
   .\bootstrap.ps1
   ```

3. 首次运行会安装 `uv`、登记 Vibe Submit Marketplace，并依次询问：学号、个人 `submit_token`、服务器地址。逐项填写教师发来的信息；服务器地址通常是 `https://vibe.planlabopc.com`。
4. 看到 `Server reachable` 与 `doctor: checks passed` 即完成。若 PowerShell 提示找不到 `uv`/`uvx`，关闭该窗口后重新开一个 PowerShell 再运行脚本。

### macOS

1. 把教师提供的 `bootstrap.sh` 保存到下载文件夹。请只运行由任课教师直接发放的脚本。
2. 打开 **终端**（Terminal），进入下载文件夹并运行：

   ```bash
   cd ~/Downloads
   bash ./bootstrap.sh
   ```

3. 首次运行会在你的用户目录安装 `uv`，不需要输入管理员密码；之后会登记 Vibe Submit Marketplace，并询问学号、个人 `submit_token` 与服务器地址。逐项填写教师私发的信息。
4. 看到 `Server reachable` 与 `doctor: checks passed` 即完成。若提示找不到 `uv`/`uvx`，关闭终端后重新打开，再运行一次 `bash ./bootstrap.sh`。

### 完成安装

完全退出并重新启动 Codex。插件菜单中应能看到 Vibe 作业提交。查看评估报告需要 Marketplace 插件 **v0.1.4 或更高版本**；若教师通知功能已更新，请重新运行课程安装脚本或在 Codex 中升级该 Marketplace 插件后再查询。

> 不要把安装命令开头的 `-ExecutionPolicy` 单独粘贴到 PowerShell；那是 `powershell` 命令的参数，会导致“无法识别”错误。

## 完成与预览作业

1. 在**作业项目根目录**内使用 Codex 完成工作。只有与该项目路径匹配的 Codex 会话会被收集。
2. 若需要交作品截图，在根目录新建 `screenshots` 文件夹，放入 `png`、`jpg`、`jpeg`、`gif`、`webp` 或 `bmp`：

   ```text
   我的作业/
   ├─ index.html
   ├─ tests/
   └─ screenshots/
      └─ 首页.png
   ```

3. 在 Codex 中说：“预览我的 Vibe 作业，并展示将提交的内容。”
4. 预览后可继续说：“打开 `code/文件路径`”或“展开会话 `session:...`”。安全预览只显示你的提示词和 Codex 最终回答，不会显示思考过程、工具输出和内部指令。
5. 确认预览正确后，明确说“确认提交”。也可在项目根目录手动提交：

   ```powershell
   vibe-submit submit --code <教师提供的作业代码> --project .
   ```

6. 工具会再次列出会话、代码、截图及大小；输入 `y` 才会上传。`Submitted successfully` 表示服务器已收到。AI 评估会异步进行，请以教师端结果为准。

## 失败重试与自检

上传中断时，包会保存在本机 outbox；网络恢复后执行：

```powershell
vibe-submit retry
```

提交前或出错时执行：

```powershell
vibe-submit doctor
```

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 只有“预览成功”的摘要 | 继续让 Codex“查看预览内容”。预览 ID 约一小时有效，过期后重新预览。 |
| macOS 显示“permission denied”或无法运行 | 使用 `bash ./bootstrap.sh`，不要双击脚本；确认脚本来自教师后再运行。 |
| 没有找到 Codex 会话 | 确认是在作业项目内使用 Codex，且会话发生在作业开放时间后；提交时 `--project` 指向根目录。 |
| 域名解析到 `198.18.x.x`、证书错误 | 关闭 VPN 的 TUN/Fake-IP 模式或换正常网络，再运行 `vibe-submit doctor`。 |
| 文件过大 | 单个文件上限 10 MB；删除依赖目录、构建产物与大文件后重新预览。 |
| 令牌无效、忘记或泄露 | 联系教师重置；不要使用同学的令牌。 |
| 已提交但教师没有马上看到评分 | 上传与 AI 评估分开进行；先确认提交成功，再等待评估队列完成。 |

## 查看评估反馈

AI 完成评估后，教师仍会先审核；只有教师发布后，报告才会对学生开放。系统不会在后台自动向 Codex 对话推送成绩。

在 Codex 中主动说“查看我的评估反馈”，或说“查看作业 `<作业代码>` 的评估反馈”。Codex 会调用课程服务器并以一条对话消息展示当前报告：

- **个人报告**：仅你本人可见，包含最终等级、评分维度、总结、改进建议及教师备注（如有）。
- **小组报告**：仅你当前所在小组的成员可见，包含团队共同等级、总结及教师备注（如有）。不会显示其他成员的个人等级、个人反馈、贡献明细、证据原文或系统内部数据。

状态为“评估中”“等待教师发布”或“未提交”时，代表尚无可查看的个人报告；不要据此推测成绩。若小组报告仍在等待发布，也不会提前显示小组等级。

也可在终端执行 `vibe-submit report --code <作业代码>`；省略 `--code` 可查看全部报告状态。报告保存在课程服务器中，新开 Codex 窗口后仍可再次查询。

## 隐私与范围

系统收集项目代码、`screenshots/` 下的图片，以及匹配项目路径的 Codex 会话。提交前请移除 `.env`、API Key、密码、个人资料和无关文件。不要将令牌、密钥或他人作品放进作业目录。
