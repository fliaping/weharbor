# WeHarbor · 微港

把微信桌面、聊天数据 API 和实时消息通知装进一个容器。

WeHarbor 是面向个人自托管的微信服务集成项目。它基于
wechat-selkies 的精简镜像，把官方 Linux 微信和 WeFlow 放在同一个
浏览器桌面里，提供窗口切换、浏览器通知，以及 WeFlow 的 HTTP API / SSE
消息推送。用户数据保存在一个 /config 卷中。

[English](docs/README.en.md) · [首次使用教程](docs/first-run.md) · [API 接入](docs/api.md) ·
[升级与迁移](docs/operations.md) · [AI skill 安装](docs/install-skill.md) ·
[组件许可](THIRD_PARTY_NOTICES.md)

## 当前状态

首版源码与本地构建版本为 0.1.0，源码仓库为
[fliaping/weharbor](https://github.com/fliaping/weharbor)。预构建镜像尚未发布。
当前组合：WeChat 4.1.13.23、WeFlow 6.3.2、wechat-selkies 0.0.14-minimal。
目前仅支持 linux/amd64；不提供未经验证的 ARM64 镜像。

WeFlow 6.3.2 的历史公开下载链接暂未确认。因此当前源码构建需要用户提供
原版安装包，或通过 WEFLOW_DOWNLOAD_URL 指定可信下载地址；校验值固定，
不会退回第三方镜像或跳过验证。公开预构建镜像发布后，使用者只需拉取镜像。

## 能力

- 在浏览器里使用官方 Linux 微信与 WeFlow，支持上游的中文输入和剪贴板。
- 悬浮窗口切换器，在微信和 WeFlow 间切换，并管理系统托盘。
- 将聊天推送与桌面通知转发为浏览器原生通知。
- 通过 WeFlow 查询会话、消息、联系人与群成员，并订阅 SSE 消息事件。
- 单容器、单数据卷；保留原版 WeFlow ASAR 和原生组件。

首次使用仍需要手机扫码登录微信，并在 WeFlow 中完成账号与数据库配置。
这里提供的数据 API 不承诺自动发送微信消息或实现机器人协议。

## 本地构建与启动

需要 Linux amd64 主机、Docker Engine、Compose v2 / Buildx 和 Python 3.10+。
获取源码后，在仓库目录执行：

~~~bash
git clone https://github.com/fliaping/weharbor.git
cd weharbor
mkdir -p downloads
cp /path/to/WeFlow-6.3.2-Setup.tar.gz downloads/weflow.tar.gz
./scripts/init.sh
./scripts/build.sh
docker compose up -d
~~~

也可在准备好安装包后运行 ./scripts/quickstart.sh，自动初始化、构建缺失的
本地镜像并启动。配置预构建镜像地址后，同一入口会拉取镜像再启动。

build.sh 会校验 WeFlow，并从微信官网下载锁定版本的 deb；也可提前把
WeChatLinux_4.1.13.23_amd64.deb 放到 downloads/wechat.deb。
官方链接会随发布变化，下载到其他版本时构建会明确失败，需要更新版本锁定文件。

打开 https://localhost:3001，使用 .env 中的 CUSTOM_USER 和 PASSWORD 登录。
首次 HTTPS 使用自签名证书。init.sh 会生成随机网页登录密码，并自动设置
宿主用户 UID/GID；已有 .env 不会被覆盖。不要把 .env 提交到 Git。

默认只绑定本机地址。需要从其他机器访问时，在 .env 设置
BIND_ADDRESS=0.0.0.0，再运行 docker compose up -d。
通过正式域名访问时，用支持 WebSocket / SSE 的 HTTPS 反向代理转发桌面端口。

预构建镜像发布后，把 .env 的 WEHARBOR_IMAGE 改成发布页给出的地址，然后：

~~~bash
docker compose pull
docker compose up -d
~~~

## 首次设置

第一次使用请按 [完整教程](docs/first-run.md) 操作，每一步都有完成标志和排障说明。

1. 先扫码登录微信，等待本地账号与聊天数据库生成。
2. 在 WeFlow 向导中自动检测数据库目录，通常为
   /config/Documents/xwechat_files（兼容链接指向 /config/xwechat_files）。
3. 获取密钥前退出微信登录、关闭自动登录；点击“自动获取密钥”，
   等 WeFlow 准备完成后再在手机上确认登录。Linux 流程会重启微信。
4. 完成配置，在 WeFlow 中打开一个会话并确认可以读到消息。图片密钥可另行配置。
5. 启用 HTTP API，使用 0.0.0.0 和 .env 中的 WEFLOW_API_PORT（默认 5031），
   生成 API Token；先查会话和消息验证读取，再安装 AI skill。

需要实时通知时再开启 WeFlow 的主动推送，并在浏览器桌面点击“启用消息通知”。
容器健康、API health 正常和 skill 安装成功，均不代表账号数据库已经可读。

浏览器通知需要 HTTPS 或 localhost，并且桌面页面保持打开。
WeFlow 的 API Token 与网页登录密码分开管理。API 默认仅映射到宿主机回环地址。

## 接入 AI 工具

仓库提供可安装的 weflow-api skill，附带无需 pip 依赖的 Python 调用脚本。
把下面的 URL 交给支持 Agent Skills、能执行命令的 AI 工具，并说
“请安装这个 skill，并帮我检查连接配置”：

https://raw.githubusercontent.com/fliaping/weharbor/main/docs/install-skill.md

也可在 AI 项目目录直接执行：

~~~bash
npx --yes skills add https://github.com/fliaping/weharbor --skill weflow-api --yes
~~~

使用者自行在 AI 执行环境配置 WEFLOW_API_BASE 与 WEFLOW_API_TOKEN，
或通过 WEFLOW_API_TOKEN_FILE 读取本地凭据文件。skill 支持聊天查询、群聊摘要、
联系人、群成员和限时 SSE 订阅；Token 不需要提交到仓库或发送到聊天中。
详细安装、联网与版本兼容说明见 [安装页](docs/install-skill.md)。

## 配置

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| WEHARBOR_IMAGE | weharbor:0.1.0 | 镜像地址与版本 |
| DATA_DIR | ./data | 持久化数据目录 |
| CUSTOM_USER / PASSWORD | 自动生成 | 浏览器桌面登录 |
| BIND_ADDRESS | 127.0.0.1 | 桌面端口绑定地址 |
| HTTP_PORT / HTTPS_PORT | 3000 / 3001 | 桌面入口 |
| API_BIND_ADDRESS | 127.0.0.1 | API 绑定地址 |
| WEFLOW_API_PORT | 5031 | 须与 WeFlow 设置一致 |
| PUID / PGID | init.sh 检测 | 持久化文件所属用户 |
| ENABLE_APP_SWITCHER | true | 悬浮切换器 |
| ENABLE_BROWSER_NOTIFICATIONS | true | 浏览器通知 |

GPU 加速可选：宿主机存在 /dev/dri 时运行
docker compose -f compose.yaml -f compose.gpu.yaml up -d。
普通部署不需要 GPU、宿主网络或特权容器；SYS_PTRACE 用于 WeFlow 的进程密钥助手。

## 开发与贡献

~~~bash
python3 scripts/check.py
./scripts/build.sh
./scripts/smoke-test.sh weharbor:0.1.0
~~~

版本、安装包 SHA256 与基础镜像 digest 集中在 versions.lock.json。
构建过程不修改 WeFlow 应用文件。root/ 只保存本项目的集成层；上游桌面与微信
启动脚本继续从基础镜像复用。

GitHub Actions 提供静态验证与测试，以及可选的构建、烟雾测试和 GHCR 发布。
部署与发布说明见 docs/operations.md。

## 许可与致谢

WeHarbor 的集成代码使用 MIT 许可证。微信、WeFlow、Selkies 及其他组件保留
各自许可；本仓库的 MIT 不会改变这些组件的使用和分发条件。
WeFlow 已公开的源码许可含非商业限制，所用 6.3.2 二进制及原生组件的授权
还需在公开镜像发布前核实。详见 THIRD_PARTY_NOTICES.md。

感谢 wechat-selkies、LinuxServer.io、Selkies 和 WeFlow 的维护者。
WeHarbor 是独立的社区集成项目。
