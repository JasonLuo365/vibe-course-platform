# Vibe Coding 作业提交：学生指南

教师会分别发送给你：

- 课程安装脚本 `bootstrap.ps1`；
- 你的个人 `submit_token`；
- 作业代码。

在 Windows PowerShell 中运行教师提供的脚本：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\bootstrap.ps1
```

首次运行时，脚本会要求输入学号和个人 token，并检查 Codex 会话目录与课程服务器连通性。

完成作业后，在作业项目根目录执行：

```powershell
vibe-submit submit --code <作业代码>
```

工具会先预览将上传的会话、代码和截图。确认无误后输入 `y` 才会提交。

若网络临时失败，提交包会保存在本机 outbox。网络恢复后可运行：

```powershell
vibe-submit retry
```

不要把 token、密码、密钥或私人文件放入作业目录，也不要将 token 转发给其他同学。

