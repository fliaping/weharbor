# 部署、更新与发布

## 数据与健康

整个 /config 目录都需要持久化，默认挂载到 ./data。
不要把微信数据库、媒体、密钥、浏览器密码或 API Token 放进镜像。

~~~bash
docker compose ps
docker compose exec weharbor weharbor-health
docker compose logs --tail=100
~~~

Docker 健康检查覆盖浏览器桌面、启用的客户端、窗口切换器与通知桥接器。
首次未配置 WeFlow API 时不会因此判定故障；启用后会额外检查 API 健康。
未登录微信或未设置数据库密钥时，容器仍可健康运行，等待用户完成配置。
首次登录、数据库密钥获取顺序及常见读取问题见 [首次使用教程](first-run.md)。

## 备份与更新

先停止容器，再备份完整数据目录及 .env：

~~~bash
docker compose stop
mkdir -p backups
tar -czf backups/profile-backup.tar.gz data .env
chmod 600 backups/profile-backup.tar.gz
docker compose start
~~~

如果修改了 DATA_DIR，请使用实际路径备份。备份包含账号数据与凭据，需要妥善保管。

预构建镜像已发布。edge 跟随 main，固定部署可使用经过测试的提交标签
（例如 ghcr.io/fliaping/weharbor:sha-06cb008）或镜像 digest。更新：

~~~bash
# 先将 .env 中的 WEHARBOR_IMAGE 设置为目标版本。
docker compose pull
docker compose up -d
docker compose exec weharbor weharbor-health
~~~

回滚时设置为旧镜像标签并重新创建容器。客户端升级可能迁移数据格式；
如旧版无法读取升级后的数据，应停止容器并恢复升级前的完整备份。

## 从旧集成迁移

1. 记录旧容器的镜像、数据挂载源路径、用户 UID/GID 和 WeFlow API 端口。
2. 停止旧容器，备份完整数据目录和部署配置。
3. 在 WeHarbor 的 .env 中把 DATA_DIR 指向该数据目录，设置原 UID/GID 和端口。
4. 启动新容器，核对微信登录、WeFlow 数据读取与浏览器通知。

同一个微信数据目录不能同时由两个容器使用。迁移保留现有 WeFlow 配置，
不会自动修改其 API Token、监听地址或推送开关。

## 初始窗口布局

WeFlow 主窗口默认最小化，微信先获得焦点。登录后只最大化当前微信进程的
一个主窗口一次；聊天、图片、设置等后续子窗口不自动最大化。用户手动还原
主窗口后，助手不会强制再次最大化。微信重启或重新创建主窗口后会重新识别。

窗口默认规则在 Openbox 配置中有 WeHarbor 标记，只替换本项目管理的规则，
保留其他窗口规则、快捷键和桌面设置。设 ENABLE_WINDOW_DEFAULTS=false
并重建容器可关闭助手；要恢复自己的 Openbox 默认行为，同时删除 rc.xml 中
WeHarbor window defaults: begin / end 之间的规则，重新加载 Openbox。
日志位于 /config/.local/log/weharbor-window-layout.log。

## 源码构建

versions.lock.json 记录准确版本、平台、基础镜像 digest 和安装包校验值。
微信 deb 和 WeFlow tar.gz 默认从本仓库的 component-assets Release 下载，
避免官网地址滚动更新版本。Release 附件仅包含原版安装包及校验清单，
不包含部署配置、账号目录或密钥。
离线构建可提前把两个安装包分别放在 downloads/wechat.deb 和 downloads/weflow.tar.gz。
WECHAT_DOWNLOAD_URL / WEFLOW_DOWNLOAD_URL 可覆盖下载地址，但仍须通过锁定校验值。
两个下载目录中的文件均不会被提交到 Git。

~~~bash
python3 scripts/prepare-assets.py
./scripts/build.sh
./scripts/smoke-test.sh weharbor:0.1.0
~~~

在网络需要时可设置 APT_MIRROR，例如 Ubuntu 的可信 HTTPS 镜像站地址。
build.sh 接受额外 Buildx 参数；一旦显式传参，需自己提供 --tag 和 --load/--push。

## GitHub Actions 与镜像发布

validate.yml 在推送和 PR 时验证脚本、配置与资产处理测试。
image.yml 在 main 推送、PR、v* 版本标签及手动触发时运行：

- main：构建并验证全新数据目录及容器重启，通过后发布 edge 和 sha-<提交>。
- PR：只构建与测试，不登录镜像仓库、不发布。
- v<版本>：与 versions.lock.json 的 project_version 一致时发布版本、latest 和 sha 标签。
- 手动：默认只构建与测试，勾选 publish 后发布当前分支对应标签。

镜像地址为 ghcr.io/<仓库所有者>/<仓库名>，使用 GitHub 自动提供的 GITHUB_TOKEN
发布 GHCR，无需把个人 Token 写入代码。Buildx 缓存与校验过的安装包缓存独立保存。
发布直接推送已经通过烟雾测试的镜像，不再重新构建。

首次运行无需额外配置，两个安装包均使用版本锁定文件中的 Release 附件地址。
需要镜像下载来源时，可在仓库 Settings → Secrets and variables → Actions → Variables
设置 WEFLOW_DOWNLOAD_URL / WECHAT_DOWNLOAD_URL；手动构建也可输入 WeFlow 的可信 HTTPS URL。
下载内容必须通过 versions.lock.json 的 SHA256 校验。地址缺失或版本不匹配时
工作流会明确失败，不会静默跳过整个镜像任务。缓存只包含 downloads 安装包，
不包含用户配置、账号数据和凭据。
fork 的发布地址自动跟随 github.repository，不绑定某个个人账号。

准备公开镜像时，应先确认原版 WeFlow 6.3.2 及所含原生组件的分发许可，
保留微信与全部第三方声明，再补充稳定可访问的安装包来源。
构建能成功并不等于已经确认所有二进制组件的再分发授权。

源码仓库：[fliaping/weharbor](https://github.com/fliaping/weharbor)。
预构建镜像 ghcr.io/fliaping/weharbor:edge 支持匿名拉取；首次通过
完整构建、空数据目录启动与重启测试的提交标签为 sha-06cb008。
