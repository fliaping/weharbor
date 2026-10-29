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
Alpha 除了桌面进程，还检查内部引擎、安全服务与数据服务；仅有空白窗口不算健康。
Alpha 的 HTTP API 未启用时不会因此判定故障；启用后 /health 会被额外检查。
未登录微信或未设置数据库密钥时，容器仍可健康运行，等待用户完成配置。
首次登录、数据库密钥获取顺序及常见读取问题见 [首次使用教程](first-run.md)。

### Alpha 空白窗口与私有目录权限

部分 NAS 的目录权限继承会把 Alpha 私有目录创建为 0705，触发其安全策略，
日志出现 SECURITY_RUNTIME_POLICY_REJECTED、application lock is unavailable
或 ENGINE_NOT_STARTED。启动器会在启动 Alpha 前修复
/config/.local/share/com.alpha.guard 与 /config/.local/state/alpha：
目录设为 0700，普通文件设为 0600，并使用 umask 077 启动应用。
修复保留文件内容，不跟随目录内的符号链接，也不修改其他应用目录或厂商程序。
无法修复时会输出具体错误并停止本次启动，请检查卷是否只读及 PUID/PGID 是否正确。
升级后通过网页重启 Alpha 或重启容器即可应用；日志位于 /config/.local/log/alpha.log。

Compose 还将容器内的 /tmp 配置为 1 GiB tmpfs，避免 NAS ACL 继承改变 Chromium
临时目录权限，导致进程锁初始化报 Socket path too long 并退出。已有部署使用
Compose 覆盖文件时，也需加入 tmpfs: ["/tmp:rw,mode=1777,size=1g"] 后重新创建容器。
直接 docker run 时使用 --tmpfs /tmp:rw,mode=1777,size=1g。这里只挂载容器的
临时目录，/config 中的登录数据与配置仍由原持久化卷保存。

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

1. 记录旧容器的镜像、数据挂载源路径、用户 UID/GID 和 API 端口。
2. 停止旧容器，备份完整数据目录和部署配置。
3. 在 WeHarbor 的 .env 中把 DATA_DIR 指向该数据目录，设置原 UID/GID 和端口。
4. 启动新容器，核对微信登录、Alpha 数据读取与浏览器通知。

同一个微信数据目录不能同时由两个容器使用。

### 从早期版本升级

新镜像首次启动时，init-weharbor-profile 会把引用旧脚本的
/config/.config/openbox/autostart 与 menu.xml 替换为新默认值（原文件保留为
*.legacy-<时间戳>），并把旧数据应用目录中的应用条与通知设置复制到 .config/weharbor。
微信登录数据保持不变；旧数据应用的配置与 Token 不会迁移，需要在 Alpha 中重新完成
首次设置并生成新的 API Token。.env 中旧的 API 端口变量改为 API_PORT，
自动启动变量改为 AUTO_START_ALPHA；自动登录与夜间重启相关变量已不再使用。
可对照 .env.example 更新。

## 初始窗口布局

Alpha 主窗口默认最小化，微信先获得焦点。登录后只最大化当前微信进程的
一个主窗口一次；聊天、图片、设置等后续子窗口不自动最大化。用户手动还原
主窗口后，助手不会强制再次最大化。微信重启或重新创建主窗口后会重新识别。

窗口默认规则在 Openbox 配置中有 WeHarbor 标记，只替换本项目管理的规则，
保留其他窗口规则、快捷键和桌面设置。设 ENABLE_WINDOW_DEFAULTS=false
并重建容器可关闭助手；要恢复自己的 Openbox 默认行为，同时删除 rc.xml 中
WeHarbor window defaults: begin / end 之间的规则，重新加载 Openbox。
日志位于 /config/.local/log/weharbor-window-layout.log。

## 网页应用管理

网页右侧默认显示一个 10px 宽的贴边小条。鼠标靠近（约 56px 内）时它会展开成
42px 的小圆球，显示当前视图的图标，离开约 0.4 秒后收回；触屏设备先轻点边缘
展开，再点圆球打开面板。系统开启“减少动态效果”时不播放过渡动画。
小条收起时只占 10px，鼠标移动只被被动监听，不影响远程桌面的输入。
拖动后自动吸附到左右边缘，位置记在当前浏览器；点击展开，点击空白处或按 Esc 收起。

切换快捷键（macOS 为 ⌃⌥⇧ 加同一按键）：

| 快捷键 | 作用 |
| --- | --- |
| Ctrl+Alt+Shift+1 | 微信桌面 |
| Ctrl+Alt+Shift+2 | 数据分析 |
| Ctrl+Alt+Shift+3 | Magpie 网关 |
| Ctrl+Alt+Shift+4 | DeepSeek 助手 |
| Ctrl+Alt+Shift+5 | 连接与操作记录 |
| Ctrl+Alt+Shift+` | 按上述顺序轮换视图 |
| Ctrl+Alt+Shift+Space | 打开或收起应用管理面板 |

快捷键按物理键位识别，焦点在远程桌面、Magpie / 助手等内嵌页面或 PWA 窗口中都有效，
命中的按键在捕获阶段被拦截，不会发送到微信等远程应用；Selkies 自带的
Ctrl+Shift+M/F/X/G 不受影响。面板中“启用切换快捷键（本浏览器）”可关闭它们。
用 `https://用户名:密码@主机/` 打开时，页面会自动去掉地址中的账号密码重新加载，
避免浏览器拒绝页面内请求。
点击应用名称切换，当前应用有多个窗口时再次点击轮换；展开窗口列表可直接
选择主窗口或子窗口。切换会最小化另一应用的窗口，不改变所选窗口的大小。
旁边的 ↻ 按钮重启对应应用，通知开关也统一放在此面板。
重启前保存未发送的内容；重启不会清除登录数据、数据库或配置，
Alpha 重启时 API 会短暂不可用。此入口沿用网页登录认证，通知关闭后仍可使用。
正常退出超时后才强制结束残留进程；同一应用的重启请求不会并行执行。

默认 APP_SWITCHER_MODE=web，不再显示旧桌面悬浮条。设为 desktop 并重建
容器可恢复旧切换器；ENABLE_APP_SWITCHER=false 关闭切换入口。

## 微信退出后的缩放兼容

部分 Linux 微信版本在桌面 DPI 改变后，退出登录时可能出现登录页绘制不完整、
花屏或按钮点击区域错位。WeHarbor 的启动器为微信固定本次进程的 Qt 逻辑 DPI，
默认采用启动时的桌面 DPI；不会修改微信原始二进制文件或自动重启已登录的客户端。
浏览器修改桌面缩放后，需要重启微信才会采用新的比例，窗口分辨率仍可自动适配。
这是兼容措施，完整登录与退出流程仍需用实际账号验证。

可在 /config/.config/weharbor/wechat-dpi 写入固定值（如 192 表示 200%），
容器重启和镜像更新会保留该设置。写入 auto 恢复启动时读取桌面 DPI；
写入 off 关闭此兼容措施。设置在下次启动微信时生效。
容器环境变量 WECHAT_FIXED_DPI 优先于此文件；已有 QT_FONT_DPI 设置保持不变。

## 源码构建

versions.lock.json 记录准确版本、平台、基础镜像 digest 和安装包校验值。
微信 deb 默认从本仓库的 component-assets Release 下载，Alpha deb 从
xunchahaha/alpha-releases 的 v0.2.0 Release 下载，避免地址滚动更新版本。Release 附件仅包含原版安装包及校验清单，
不包含部署配置、账号目录或密钥。
离线构建可提前把两个安装包分别放在 downloads/wechat.deb 和 downloads/alpha.deb。
WECHAT_DOWNLOAD_URL / ALPHA_DOWNLOAD_URL 可覆盖下载地址，但仍须通过锁定校验值。
两个下载目录中的文件均不会被提交到 Git。

~~~bash
python3 scripts/prepare-assets.py
./scripts/build.sh
./scripts/smoke-test.sh weharbor:0.1.0
~~~

在网络需要时可设置 APT_MIRROR，例如 Debian 的可信镜像站根地址（替换 http://deb.debian.org/）。
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
设置 ALPHA_DOWNLOAD_URL / WECHAT_DOWNLOAD_URL；手动构建也可输入 Alpha 的可信 HTTPS URL。
下载内容必须通过 versions.lock.json 的 SHA256 校验。地址缺失或版本不匹配时
工作流会明确失败，不会静默跳过整个镜像任务。缓存只包含 downloads 安装包，
不包含用户配置、账号数据和凭据。
fork 的发布地址自动跟随 github.repository，不绑定某个个人账号。

准备公开镜像时，应先确认 Alpha 0.2.0（闭源、许可未声明）及所含组件的分发许可，
保留微信与全部第三方声明，再补充稳定可访问的安装包来源。
构建能成功并不等于已经确认所有二进制组件的再分发授权。

源码仓库：[fliaping/weharbor](https://github.com/fliaping/weharbor)。
预构建镜像 ghcr.io/fliaping/weharbor:edge 支持匿名拉取；首次通过
完整构建、空数据目录启动与重启测试的提交标签为 sha-06cb008。

## 本机（无 systemd）运行提示

在没有 systemd 的主机上，dockerd 与 tailscaled 需要手动拉起；容器使用
restart: unless-stopped，dockerd 启动后会自动恢复。Tailscale Serve 配置保存在
tailscaled 状态目录中，重启 tailscaled 后仍生效。

## proot-apps

WeChat and Alpha are not installed as proot-apps: Alpha's key helper refuses to run under proot. See [proot-apps-evaluation.md](proot-apps-evaluation.md).
