# 安装 WeFlow API skill

把本页 URL 交给支持 Agent Skills、能执行命令的 AI 工具，并说：
“请安装这个 WeFlow API skill，并帮我检查连接配置。”

本页公开地址：
https://raw.githubusercontent.com/fliaping/weharbor/main/docs/install-skill.md

## 给 AI 安装者的步骤

用户要求通过本页安装时，请读取
[SKILL.md](https://raw.githubusercontent.com/fliaping/weharbor/main/skills/weflow-api/SKILL.md)，
再安装整个 skill 目录。技能源码位于
https://github.com/fliaping/weharbor/tree/main/skills/weflow-api 。
只保存 SKILL.md 会缺失调用脚本。

1. 在用户选择的项目目录执行以下命令；安装器会识别可用的 AI 工具。
   已知当前工具时可加 --agent codex、--agent claude-code 等对应参数。
   默认安装到项目；用户要求全局安装时再加 --global。

   ~~~bash
   npx --yes skills add https://github.com/fliaping/weharbor --skill weflow-api --yes
   ~~~

2. 如果没有 Node.js，克隆仓库，再把 skills/weflow-api 整个目录复制到当前
   AI 工具支持的 skills 目录。检查已有同名 skill，保留用户定制内容。
3. 找到安装后的目录，运行：

   ~~~bash
   python3 <skill-dir>/scripts/weflow_api.py --help
   python3 <skill-dir>/scripts/weflow_api.py health
   ~~~

4. 使用者在本地配置 WEFLOW_API_BASE 和 WEFLOW_API_TOKEN，或用
   WEFLOW_API_TOKEN_FILE 指向本地凭据文件。通过工具自己的环境变量或
   secret 设置注入；不要要求用户把真实 Token 发到聊天中。
5. 读取 SKILL.md 后先检查 health，再查询少量 sessions 验证鉴权。
   缺少地址或凭据时，报告尚未完成连接配置，不能声称已经可读取微信数据。

Python 3.10+ 即可调用 API，无需 pip 依赖。某些工具需要新会话才能加载 skill。
只支持聊天、不能执行脚本或加载技能的 AI 产品无法仅靠粘贴 URL 完成安装。

## 连接自己的微信

先在 WeFlow 中配置微信账号、数据库密钥并启用 HTTP API；实时订阅还需开启
主动推送。API Token 与 WeHarbor 的浏览器登录密码不同。
第一次安装 WeHarbor 时，请先完成 [首次使用教程](first-run.md)，
在 WeFlow 内确认消息可读。Linux 获取密钥需等待准备完成后再确认微信登录；
skill 不会替用户扫码登录、获取数据库密钥或自动配置 WeFlow。

默认 API 地址为 http://127.0.0.1:5031。这个地址指 AI 执行环境自身：远程
AI 无法通过它连接使用者电脑。需要通过可信网络、VPN 或 SSH 隧道到达实际
WeFlow 服务，并保留鉴权。WeHarbor 同网络的其他容器可使用 http://weharbor:5031。
无需公开自己的服务地址或凭据到这个 GitHub 仓库。

安装完成后，可以说：“找到项目群，汇总今天的讨论与待办”，或
“订阅接下来 30 秒的新消息”。skill 支持会话、消息、联系人、群成员、
ChatLab、可用版本的朋友圈接口、媒体下载和有时间限制的 SSE 订阅。

更新时重新执行安装命令，或使用 npx skills update weflow-api。
源代码使用本仓库 MIT 许可，安装不会改变微信和 WeFlow 的组件许可。
