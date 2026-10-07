# API 接入

AI 工具可安装仓库自带的 [weflow-api skill](install-skill.md)，
通过 Python 客户端执行下面的查询，并使用本地环境变量管理凭据。

API 由原版 WeFlow 提供。先在设置中启用 HTTP API，设置监听地址为 0.0.0.0、
端口为 Compose 配置的 WEFLOW_API_PORT，并生成 Token。
Compose 只负责端口映射，不会覆盖 WeFlow 的持久化设置。
首次接入前，先按 [首次使用教程](first-run.md) 完成数据库密钥配置并在
WeFlow 界面确认消息可读。服务已启动时需先关闭，再编辑监听地址和端口。

下面的例子从环境变量读取 Token；请在本地设置 WEFLOW_API_TOKEN。
不要把实际 Token 放入文档、源码或公开日志。

~~~bash
# 健康检查不需要 Token。
curl --fail http://127.0.0.1:5031/health

# 查询会话。
curl --fail -H "Authorization: Bearer $WEFLOW_API_TOKEN" \
  http://127.0.0.1:5031/api/v1/sessions

# 查询联系人。
curl --fail -H "Authorization: Bearer $WEFLOW_API_TOKEN" \
  http://127.0.0.1:5031/api/v1/contacts

# 订阅实时消息，使用请求头传递 Token。
curl --no-buffer \
  -H "Authorization: Bearer $WEFLOW_API_TOKEN" \
  http://127.0.0.1:5031/api/v1/push/messages
~~~

API 也接受 access_token 查询参数；界面生成的 SSE 地址可能包含它。
使用这类地址时，反向代理访问日志应避免记录原始查询串。
消息推送还需要在 WeFlow 设置中开启主动推送。

| 接口 | 用途 |
| --- | --- |
| GET /health | API 存活检查 |
| GET /api/v1/sessions | 会话列表 |
| GET /api/v1/messages | 按条件查询消息 |
| GET /api/v1/contacts | 联系人 |
| GET /api/v1/group-members | 群成员 |
| GET /api/v1/push/messages | 实时消息 SSE |

详细参数和响应结构以所用 WeFlow 版本为准。当前集成侧重本地聊天数据读取、
查询与事件订阅。客户端在线并不代表账号数据库已经配置成功。
health 只检查服务存活。继续带 Token 查询 sessions，再使用返回会话的
username 作为 messages 的 talker 查询少量消息，才完成读取验证。

其他容器接入时，建议让它们与 WeHarbor 使用同一个自定义 Docker 网络，
通过服务名 weharbor:5031 访问；外部调用仍需使用 WeFlow Token。
桌面反向代理需要转发 WebSocket，并关闭 /notifications/ 路径的响应缓冲。
