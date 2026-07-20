# 学生指南

教师会私密发送作业代码和你的个人 `submit_token`，并公开发送 `bootstrap.ps1`。令牌相当于提交密码，不得截图、转发或上传至 Git。

## 安装

在保存了 `bootstrap.ps1` 的文件夹中打开 Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\bootstrap.ps1
```

首次运行会安装 `uv`、注册 Codex 插件，并要求输入服务器、学号和令牌。完成后运行：

```powershell
vibe-submit doctor
```

应看到 `Server reachable`。若刚装完没有插件，彻底退出并重新打开 Codex。

## 提交

在作业项目根目录使用 Codex 完成作业。需要图片时，在根目录创建 `screenshots/`，将 png/jpg/jpeg/gif/webp/bmp 图片放入其中。然后在 Codex 中要求“预览 Vibe 作业并展示内容”；可继续要求打开 `code/文件路径` 或展开某一会话。预览只会显示提示词和最终回答，不含思考过程或工具输出。

确认后要求“确认提交”，或执行：

```powershell
vibe-submit submit --code <作业代码> --project .
```

输入 `y` 才会上传。失败的包会保存在 outbox，联网后执行 `vibe-submit retry`。

## 常见问题

- 只有预览摘要：让 Codex 继续“查看预览内容”；预览 ID 有效约一小时，过期后重新预览。
- 没有会话：须在作业项目内使用 Codex，并在作业开放后创建会话。
- DNS 显示 `198.18.x.x`、证书错误：关闭 VPN 的 TUN/Fake-IP 模式后重新运行 `vibe-submit doctor`。
- 忘记或泄露令牌：联系教师重置；旧令牌会立即失效。
- 文件太大：单文件上限 10 MB；删除构建产物、依赖目录、密钥和大文件后再预览。

提交前务必检查预览，勿把 `.env`、API Key、密码或私人文件放在项目内。
