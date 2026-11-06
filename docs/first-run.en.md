# First run: from WeChat login to asking the assistant

Applies to WeHarbor 0.1.0 with WeChat 4.1.13.23, Selkies 2.0 and the pinned
`fliaping/WeChatDataAnalysis` (see versions.lock.json). Button labels in the
analysis UI may differ slightly. A passing container smoke test does not verify
key acquisition with a real account.

[中文](first-run.md)

1. **Open the workspace** at `https://localhost:3001` with `CUSTOM_USER`/`PASSWORD`
   from `.env`. The left rail is WeChat / Analysis / Assistant / Magpie /
   Connections (Alt+1–5; Option on macOS).
2. **Log in to WeChat** by scanning the QR code (or pressing 登录 for a saved
   account) and confirming on the phone.
3. **Get the database key in Analysis** (Alt+2). A verified WeFlow key for the
   account is reused without attaching to WeChat. Otherwise start key capture
   on the Linux source card, then log out of WeChat and back in within 120
   seconds. The key is validated by decrypting before it is saved under
   `/config/.local/share/weharbor/analysis`. The container needs `SYS_PTRACE`
   (set in compose.yaml). Image keys are captured and validated the same way.
4. **Add a model provider in Magpie** (Alt+4). Magpie redacts secrets and
   personal data locally before model calls; models sync to the assistant
   within about 15 seconds.
5. **Ask the assistant** (Alt+3). It reads chats through the local MCP tools;
   sending requires an explicit prepare and commit. External AI tools can use
   `https://<host>/workspace/mcp` with the token in
   `/config/.config/weharbor/workspace.token` (see [workspace.md](workspace.md)).

Upgrading from an image that still shipped Alpha: Alpha, its API on port 5031,
the alpha-api skill and the Alpha token are gone. Remove `API_BIND_ADDRESS`,
`API_PORT` and `AUTO_START_ALPHA` from `.env`. Old Alpha files in the data
directory can be deleted manually.
