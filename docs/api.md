# API 接入

AI 工具可安装仓库自带的 [alpha-api skill](install-skill.md)，
通过 Python 客户端执行下面的查询，并使用本地环境变量管理凭据。

API 由原版 Alpha 0.2.0 提供，需先在 Alpha 设置中启用 HTTP API（端口 5031）并生成
Token。Alpha 只监听容器内的 127.0.0.1，并拒绝 Host 不是 `127.0.0.1:5031` /
`localhost:5031` 或带 Origin 头的请求。WeHarbor 在容器内用 nginx 监听
`ALPHA_API_PROXY_PORT`（默认 5032）转发并改写 Host，同时拒绝带 Origin 的请求；
Compose 把它映射到宿主机 `${API_BIND_ADDRESS}:${API_PORT}`（默认 127.0.0.1:5031）。
首次接入前，先按 [首次使用教程](first-run.md) 完成 Alpha 向导并确认消息可读。

~~~bash
# 健康检查不需要 Token。
curl --fail http://127.0.0.1:5031/health

curl --fail -H "Authorization: Bearer $ALPHA_API_TOKEN" http://127.0.0.1:5031/api/v1/sessions
curl --fail -H "Authorization: Bearer $ALPHA_API_TOKEN" http://127.0.0.1:5031/api/v1/contacts

# 实时消息 SSE（需在 Alpha 中开启主动推送）。
curl --no-buffer -H "Authorization: Bearer $ALPHA_API_TOKEN" \
  http://127.0.0.1:5031/api/v1/push/messages
~~~

API 也接受 `access_token` 查询参数；反向代理日志应避免记录原始查询串。

| 接口 | 用途 |
| --- | --- |
| GET /health, /api/v1/health | 存活检查（无需 Token） |
| GET /api/v1/accounts | 账号 |
| GET /api/v1/sessions | 会话列表 |
| GET /api/v1/sessions/{id}/messages | 会话消息（ChatLab 分页） |
| GET /api/v1/messages | 按条件查询消息 |
| GET /api/v1/search | 搜索 |
| GET /api/v1/contacts | 联系人 |
| GET /api/v1/group-members | 群成员 |
| GET /api/v1/sns/timeline 等 | 朋友圈 |
| GET /api/v1/media/... | 媒体 |
| GET /api/v1/exports, /api/v1/exports/formats | 导出 |
| GET /api/v1/push/messages | 实时消息 SSE |
| POST /mcp | MCP（Streamable HTTP）；也可用 /opt/Alpha/resources/bin/alpha-mcp-stdio |
| POST /api/v1/messages/send-text | 发送文本消息（Alpha 能力，谨慎授权） |

路由列表来自 Alpha 0.2.0 安装包的静态分析，参数与响应结构尚未在真实实例上核对。
health 只检查服务存活；带 Token 查询 sessions 并读取少量消息才算完成验证。

其他容器接入时，可与 WeHarbor 使用同一 Docker 网络，通过 `weharbor:5032` 访问；
请求仍需 Alpha Token，且不能带 Origin 头。
