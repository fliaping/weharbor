# 安装为桌面应用

WeHarbor 可以安装为 PWA，以独立窗口从电脑桌面或手机主屏幕打开。
应用名称为 **WeHarbor｜微港**。微信和 WeFlow 仍在服务器上运行，需要在线连接。

## 使用条件

- 使用可信证书的 HTTPS 地址。HTTP 的局域网 IP 地址不支持安装。
- 本机测试可使用 http://localhost；忽略自签名证书警告不等于可信 HTTPS，
  浏览器仍可能禁止 Service Worker 或隐藏安装入口。
- 先完成原有网页登录认证。安装不会跳过密码、外层网关认证或 API Token。
- 反向代理保留 WebSocket / SSE 支持，并允许同一桌面路径下的 manifest、
  JS 与图标请求；不要把这些请求改写成网关登录页。

## 电脑和 Android

用 Chrome 或 Edge 打开桌面，等页面加载后点击右下角 **安装 WeHarbor**，
确认浏览器安装对话框。也可以使用浏览器地址栏或菜单里的“安装应用”。
按钮在浏览器发出可安装事件时显示，已安装的独立窗口内会隐藏。
不支持安装事件的浏览器可尝试其“添加到主屏幕”菜单。

## iPhone 和 iPad

在 Safari 中打开桌面，点击 **安装 WeHarbor** 查看操作提示，
然后点击 Safari 的分享按钮，选择 **添加到主屏幕**。
这一步需要用户在 Safari 中确认，网页无法代替系统执行安装。

## 更新与离线

安装后仍使用同一个服务器地址。更新容器后关闭并重新打开应用，
或刷新页面以加载新版本。安装脚本与 Service Worker 会重新检查更新。
改名之前已经安装的图标可能保留旧名称，删除旧图标后重新安装即可。

Service Worker 只为离线导航提供重新连接提示，不保存聊天消息、
桌面画面、文件、API 或通知响应，也不拦截 WebSocket / SSE。
断网时无法操作微信；网络和服务器恢复后点击 **重新连接**。

## 检查安装入口

在浏览器开发者工具的 Application 面板检查：

1. Manifest 为 weharbor.webmanifest，名称正确，192px / 512px 图标可读取。
2. Service Worker 为 weharbor-sw.js，状态已激活，scope 对应桌面路径。
3. 地址使用可信 HTTPS，manifest、Worker、图标没有 401、重定向登录页或 404。

安装入口取决于浏览器策略；已经安装、使用隐私窗口或受组织策略限制时，
可能没有安装按钮。子路径部署使用上游 SUBFOLDER（末尾保留 /），
manifest 的 id、start_url、scope 都相对于该路径，避免打开网站根目录。
