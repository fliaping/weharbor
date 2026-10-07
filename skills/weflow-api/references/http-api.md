# API notes

Endpoint definitions: [upstream HTTP API documentation](https://github.com/hicccc77/WeFlow/blob/837697ba26605152f216bd5ffc5e9d61aa9f2907/docs/HTTP-API.md).
WeHarbor pins WeFlow 6.3.2; upstream documentation can include newer optional
features. A 404 should be reported as unsupported, not silently replaced by
another operation. The helper uses GET and Bearer authentication, including SSE.

| Helper command | Endpoint | Output / useful parameters |
| --- | --- | --- |
| health | /health | status; no token sent |
| sessions | /api/v1/sessions | sessions; keyword, limit |
| messages | /api/v1/messages | messages, count, hasMore; talker, start, end, keyword, limit, offset |
| contacts | /api/v1/contacts | contacts; keyword, limit |
| group-members | /api/v1/group-members | members; chatroomId, includeMessageCounts |
| chatlab-sessions | /api/v1/sessions?format=chatlab | sessions with id |
| chatlab-messages | /api/v1/sessions/{id}/messages | messages and sync; since, end, limit, offset |
| sns-timeline | /api/v1/sns/timeline | timeline; usernames, keyword, limit, offset, start, end |
| sns-usernames | /api/v1/sns/usernames | available usernames |
| sns-export-stats | /api/v1/sns/export/stats | statistics; fast=1 |
| media | /api/v1/media/{relativePath} | binary download to an explicitly chosen output file |
| sse | /api/v1/push/messages | message.new / message.revoke events as JSON lines |

## Time windows and pagination

For messages and timeline filters, use YYYYMMDD or Unix timestamps. The helper
normalizes ten-digit Unix seconds to milliseconds for compatibility with older
message-filter builds, and preserves thirteen-digit milliseconds. Returned
createTime and SSE timestamp are normally seconds. Date-only filters use the
WeFlow host's timezone; date-only end includes that whole day. Confirm the user's
timezone before computing a window (WeHarbor's default is Asia/Shanghai).

If an expected timestamp query is empty, retry the surrounding YYYYMMDD window,
paginate fully, then locally filter createTime to the exact requested interval.
Do not summarize the broader window without that filtering. Dates must be valid;
other time string formats are rejected by the helper.

~~~bash
python3 <skill-dir>/scripts/weflow_api.py messages --talker example@chatroom --start 20261001 --end 20261007 --limit 100 --offset 0
python3 <skill-dir>/scripts/weflow_api.py chatlab-messages --session-id example@chatroom --since 1790812800 --limit 100
~~~

Follow hasMore for ordinary messages. ChatLab uses sync.hasMore, nextOffset and
nextSince; continue with the same since and the next offset during a pull, then
retain the returned watermark for a later sync. Report incomplete/truncated
results. There is no unlimited automatic history crawl.

## Media and streaming

messages --media asks WeFlow to export media files, which can write its local
media cache. Only enable this when attachments are needed. Take the relative
path following /api/v1/media/ from a returned mediaUrl; pass it to media with
--output. The helper sends authentication only to the configured API base,
rejects redirects, and refuses to overwrite an existing output file.

SSE defaults to a 30-second observation window and at most 20 events. Both are
configurable; an idle stream timeout is a normal end. Deduplicate downstream by
event plus data.rawid. An empty observation window does not prove no history
exists. Use --last-event-id for replay only when the deployed version supports it.
The client uses the Authorization header rather than putting the token in a URL.
