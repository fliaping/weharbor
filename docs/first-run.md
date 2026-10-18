# 首次使用：从登录微信到读取第一条消息

本页适用于 WeHarbor 0.1.0 的组合：WeChat 4.1.13.23、Alpha 0.2.0、Selkies 2.0。
Alpha 向导第一步之后的界面文字尚未在本项目中逐一核对，以实际界面为准。
先按 [README](../README.md#本地构建与启动) 完成构建和启动，再从这里继续。

[English](first-run.en.md)

Alpha 通过读取本机微信进程内存获取数据库密钥，再只读打开该账号的本地聊天数据库。
手机扫码登录、获取密钥、API 鉴权是三个独立步骤；安装 skill 不会替你完成前两步。

| 阶段 | 完成标志 |
| --- | --- |
| 打开桌面 | 能在浏览器中看到微信和 Alpha 窗口 |
| 登录微信 | 微信会话列表出现，本地账号数据已生成 |
| 连接微信 | Alpha 向导识别到账号与数据目录并取得数据库密钥 |
| 读取数据 | Alpha 完成向导，能打开一个会话并看到消息 |
| 开启 API | health 正常，带 Token 能查询会话和消息 |
| 接入 AI | AI 所在环境能访问 API，并成功读取少量消息 |

## 1. 打开浏览器桌面

在 Docker 主机上打开 `https://localhost:3001`，使用 `.env` 中的
`CUSTOM_USER` 和 `PASSWORD` 登录。首次使用自签名证书时，核对地址后继续。
在其他电脑访问可使用 SSH 隧道（`ssh -N -L 3001:127.0.0.1:3001 user@host`）
或 Tailscale Serve（`tailscale serve --bg --https=443 https+insecure://127.0.0.1:3001`，仅 tailnet 可见）。

微信和 Alpha 会自动启动，Alpha 初始最小化。点击网页右侧的小条展开应用管理切换窗口。
容器 healthy 只代表程序和桌面服务正常，不代表已经能读取聊天记录。

## 2. 登录微信

1. 切换到微信，用手机扫码（已有账号时点击“登录”），在手机上确认。
2. 等待会话列表和近期消息加载，打开一个熟悉的会话确认有文字消息。

Alpha 能读取的是这个 Linux 微信实例已保存在本地的数据，手机上的全部历史不会自动出现。
本版本已移除旧镜像的“自动点击登录”，容器重启后可能需要在手机上再次确认。

## 3. 完成 Alpha 首次设置向导

向导分为“连接微信”“获取图片密钥”“完成”三步：

1. 在“连接你的微信”页勾选“我已了解，开始连接本地数据”，点击“连接微信”。
2. 选择账号与数据目录。本项目的路径为 `/config/Documents/xwechat_files`
   （兼容链接，指向 `/config/xwechat_files`）。
3. 按提示获取数据库密钥。微信需保持登录；Alpha 的密钥助手以同一用户读取微信
   进程内存，Compose 已添加 SYS_PTRACE。
4. “获取图片密钥”可跳过，需要查看聊天图片时再配置。
5. 完成后打开一个会话，确认能看到消息。

Alpha 的 HTTP API Token 由 Electron safeStorage 加密保存。容器在桌面会话中自动启动
无密码的 gnome-keyring（`/config/.local/share/keyrings`），因此不会弹出密钥环密码框；
Token 的安全性依赖数据目录的访问控制。

## 4. 开启 HTTP API

在 Alpha 设置中启用 HTTP API，端口保持 5031，生成并复制访问 Token。
需要实时消息时同时开启主动推送。验证：

~~~bash
curl --fail http://127.0.0.1:5031/health
curl --fail -H "Authorization: Bearer $ALPHA_API_TOKEN" http://127.0.0.1:5031/api/v1/sessions
~~~

宿主机的 5031 实际映射到容器内 nginx 的 5032 端口，再转发到 Alpha 的
127.0.0.1:5031。浏览器通知需要把 Token 写入
`/config/.config/weharbor/alpha-api-token`（权限 600）。

## 5. 接入 AI

按 [安装页](install-skill.md) 安装 alpha-api skill，并在 AI 执行环境配置
ALPHA_API_BASE / ALPHA_API_TOKEN。先查少量 sessions，再查一个会话的消息。

## 常见问题

- 出现“Choose password for new keyring”弹窗：说明密钥环未正确初始化，
  重启 Alpha（应用条中的重启按钮）后应消失。
- API 返回 403 `HTTP_API_HOST_DENIED` / `HTTP_API_ORIGIN_DENIED`：不要绕过容器内
  代理直接访问，也不要从浏览器页面发起请求。
- 密钥获取失败：确认微信已登录；Alpha 的密钥助手内置有效期
  （0.2.0 为 2026-11-15），过期后需升级 Alpha。
