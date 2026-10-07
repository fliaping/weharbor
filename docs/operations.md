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

预构建镜像发布后，使用固定版本标签更新：

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

## 源码构建

versions.lock.json 记录准确版本、平台、基础镜像 digest 和安装包校验值。
微信官方的下载链接会变化；旧包可缓存在 downloads/wechat.deb。
WeFlow 包可放在 downloads/weflow.tar.gz，或通过 WEFLOW_DOWNLOAD_URL 下载。
两个下载目录中的文件均不会被提交到 Git。

~~~bash
python3 scripts/prepare-assets.py --check-only
./scripts/build.sh
./scripts/smoke-test.sh weharbor:0.1.0
~~~

在网络需要时可设置 APT_MIRROR，例如 Ubuntu 的可信 HTTPS 镜像站地址。
build.sh 接受额外 Buildx 参数；一旦显式传参，需自己提供 --tag 和 --load/--push。

## GitHub Actions 与镜像发布

validate.yml 在推送和 PR 时验证脚本、配置与资产处理测试。
image.yml 支持手动构建：输入可信 WeFlow 下载 URL，默认只构建和测试；
明确选择 publish 后才向当前仓库对应的 GHCR 地址推送。
若配置仓库变量 WEFLOW_DOWNLOAD_URL，版本标签推送也可执行镜像发布。
fork 的发布地址自动跟随 github.repository，不绑定某个个人账号。

准备公开镜像时，应先确认原版 WeFlow 6.3.2 及所含原生组件的分发许可，
保留微信与全部第三方声明，再补充稳定可访问的安装包来源。
构建能成功并不等于已经确认所有二进制组件的再分发授权。

源码仓库：[fliaping/weharbor](https://github.com/fliaping/weharbor)。
当前仅发布集成源码，预构建镜像尚未发布。
