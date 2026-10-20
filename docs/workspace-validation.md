# Workspace validation — 2026-10-20

Validated on an amd64 Linux NAS with an existing WeHarbor profile. Test output
contains counts and status only; keys, chat contents and account identities are
not committed. The preceding baseline image was
`sha256:5e7b6ef5b43e12e135251d23f51076e6b81a540c507a43e2c59584f67ceb5d7c`.
The historical build reports below describe their deployment state at the time.

## October 20 agreement removal

Analysis revision `61b31433d18bb638b5f51dbdeb1a461c16d84cfe` removes the
first-use notice, disclaimer, countdown, bootstrap redirect and route guard.
Existing `/analysis/agreement` bookmarks return immediately to the analysis
home page. Account loading, privacy settings and desktop updates initialize
without requiring an agreement flag in browser storage.

Frontend validation passed 66 Node tests, 116 Vitest tests and a production
static build under `/analysis/`. A fresh browser rendered the hydrated home
and advanced pages without the agreement overlay; the legacy agreement URL
returned to the home page. WeHarbor source validation passed all 162 tests.

## October 20 unified build

The unified source combines the advanced workspace, continuous Moments archive,
analysis automation and DeepSeek Harness integration with the verified-session
navigation, visual Send driver and Linux snapshot event synchronization.
The analysis source is pinned to `d747ca5631031265157b10d6f6a7402a19173aa4`.

- WeHarbor source validation: 162 tests passed. Analysis backend: 65 tests and
  28 subtests passed. Frontend: 71 Node tests and 116 Vitest tests passed.
- The merged MCP inventory has 35 WeHarbor tools and 19 analysis tools. Both
  filesystem Skills are registered with the official DeepSeek Harness runtime.
- All 79 advanced feature entries are accessible; 48 have code execution paths,
  while 31 remain explicitly unimplemented. Execution paths do not establish
  real-account success. No message was sent or task activated during validation.
- Desktop navigation retains draft protection and exact original-process session
  verification. Mark-read persists its action boundary before selecting a chat.
- Image: `weharbor:unified-20261020`,
  `sha256:ca95c2c69cfd11c8601e3f9fb1c2aa87058916290b518a1ec1b9a1a8ebb6ebb1`,
  built from WeHarbor revision `df9a0f620a352b01cd3493f64f9b3ccfb316ce3b`.
  The private gzip export is 2,516,228,362 bytes, SHA256
  `fc546302a73418bcd038f707969ce0dd30590a4d84a6058d607b25b69b949dfc`.
- Full fresh-profile smoke passed: both MCP inventories, both Harness filesystem
  Skills and active MCP plugins, private upload streaming, browser authentication,
  foreign-origin rejection, application switching, structured desktop readiness,
  original vendor program verification and repeatable container restart.
  Skill discovery uses the pinned Harness RPC descriptors (`session/create` and
  `skills/list`, with named `request` arguments). No model request was made.
- NAS deployment passed with the same image ID. The existing `/config` mount
  and port bindings were preserved, a full stopped-profile backup was taken,
  and the preceding image was retained as `weharbor:before-unified-20261020`.
  Health, all five authenticated pages, both MCP inventories, both active Harness
  plugins, both discoverable Skills and the Linux snapshot SSE stream passed.
  The existing account remains present. WeChat currently reports
  `WECHAT_LOGIN_REQUIRED`; desktop writes require the owner's login or phone
  confirmation. No message was sent and no automation task was activated.

## October 20 labels and onboarding build — local, not deployed

- Image: `weharbor:workspace-20261020-labels`,
  `sha256:e2fa9ac0e53779c84080c2937769150da09418d9be5c026151251cfc117603fd`.
  Analysis snapshot: `9ba2b71dc1b8018ab7feb59b028713beeb314f1b+workspace.fa7ab7756ee2`;
  source archive SHA256: `fa7ab7756ee23792d85c59db9cbb750043bb366961f62e51bf34144bb754228b`.
  Canonical component pins and the original WeChat/Alpha programs are preserved.
  The private Docker export is 2,336,900,251 bytes, SHA256
  `acef74b22ecc49ce1640a03efa1abf7d4370b0ae1e125876ea1af5456f53bd30`;
  its manifest and config digest match the tested image ID above.
- Added complete label-list reads and create, set, rename and delete operations.
  Exact names, contact/account identity and complete accessible lists are required.
  Existing user dialogs are preserved, changed preparation snapshots cancel the
  operation, and writes require a fresh readback. Empty selections clear the
  contact's labels; deleting a label never deletes contacts. Unsupported Qt
  layouts fail rather than guessing. These controls still need real account validation.
- Onboarding now supports explicit chat navigation before remark, label and
  welcome-message steps. Activation records a complete contact baseline; only
  later friends trigger it, optionally restricted to exact target usernames.
  Incomplete snapshots and account mismatches fail; seen contacts and step
  receipts survive restart without replay. No task was activated on a real account.
- The matching free workbench has 46 / 79 code execution paths and 32 WeChat
  MCP tools. The other 33 features still lack WeChat execution drivers. A form,
  capability flag or synthetic test does not establish working real-account behavior.
- WeHarbor source validation: 118 tests passed. Analysis advanced backend:
  42 tests and 23 subtests passed. Frontend: 71 Node and 113 Vitest tests passed.
  Production generation completed with 41 routes. New coverage includes label
  replacement/clearing, rejected saves, duplicate and partial lists, draft
  preservation, preparation races, contact baselines and target filtering.
- Fresh-profile image smoke and container restart passed: 46-path discovery,
  32 authenticated WeChat MCP tools, the six-tool authenticated read-only
  analysis stdio bridge, private streaming uploads, browser authentication,
  foreign-origin rejection, app switching and pinned vendor verification.
  Harness starts with both MCP clients. No WeChat action was submitted.
- This image has not replaced the NAS deployment described below. The previous
  local image and export remain available for comparison and rollback.

## Earlier October 20 advanced build — local, not deployed

- Image: `weharbor:workspace-20261020`,
  `sha256:36c1a6efa36a3c4f51a5067ae6ac8643d4a8239b539bdc58f5a0852c5b64eeaa`.
  Analysis snapshot: `9ba2b71dc1b8018ab7feb59b028713beeb314f1b+workspace.990540b8902a`;
  archive SHA256: `990540b8902a2f8e62f47eb2680810bb3d293c4c8e221d09163e2b7ee0b9f35f`.
  Canonical component pins and original WeChat/Alpha programs were preserved.
  The private Docker export is 2,342,975,536 bytes, SHA256
  `5cf270d7af65e5be6bdaf4da470787986e159f46cb346dfe1cbcdf5f684d029a`;
  its manifest was checked against the image ID above.
- Nine additional desktop execution paths: file, image and video sends; mark
  read; mute; contact remark; group name, own group nickname and notice.
  The free feature inventory now has 40 / 79 execution paths. The remaining
  39 still need WeChat drivers; publishing a form or binding does not implement them.
- WeHarbor source validation: 106 tests passed. Analysis advanced backend:
  37 tests and 20 subtests passed. Frontend: 71 Node and 109 Vitest tests passed.
  Production generation completed with 41 routes. Synthetic tests cover wrong
  targets, changed bytes/context, durable submission boundaries, uncertain
  receipts, shared idempotency keys and permissions inherited from NAS volumes.
- Fresh-profile image smoke and container restart passed. Verified 40-path
  capability discovery, a 2.1 MiB browser-to-analysis-to-workspace streaming
  upload with exact-byte and private-mode checks, 27 authenticated WeChat MCP
  tools, and the separate authenticated six-tool read-only analysis stdio bridge.
  Harness starts with both MCP clients. Browser auth, foreign-origin rejection,
  app restart/switching, PWA resources and pinned vendor verification passed.
- The first local smoke exposed Chromium singleton initialization failing on
  inherited temporary-directory permissions. Compose and the final smoke use
  a container-only 1 GiB /tmp tmpfs; Alpha startup and repeatable restart then
  passed. Upload directories are explicitly chmod 0700, files 0400, and the
  analysis MCP token is tightened to 0600 on creation and reuse.
- No real account operation was prepared or submitted. Actual logged-in Qt
  controls, attachment transformations and settings persistence still need
  account validation. Synthetic receipts are not evidence of recipient delivery.
- NAS 192.168.217.6:3000 still serves the preceding deployment: workspace health
  returns 200, the advanced capabilities route returns 404, and SSH port 22
  refuses connections. A usable SSH endpoint is needed to deploy and inspect
  the real instance. No production profile or service was changed by this update.

## October 20 navigation and recovery validation

- Passed 118 integration/source tests, covering exact-result navigation, duplicate
  titles, exclusion of history/message results, draft and manual-search
  preservation, structured recovery, pre-input retry, context cancellation,
  expiration during navigation and no retry after attempted composer writes.
- On the unlocked NAS, the new driver opened the authorized target from the
  Contacts page and verified its exact original-process session. It cleared only
  its own search query. An owned synthetic draft blocked navigation and readiness
  checks and remained unchanged; after removing only that draft, readiness
  recovered. No message was sent during these navigation/recovery checks.
- MCP now exposes fourteen tools, including read-only desktop readiness and
  exact-target navigation. Scheduled transient pre-input failures may recover
  for at most five minutes after due time; changed context cancels the action.
  Expiry is checked again before editor writes and submission.
- Authenticated HTTP and MCP both navigated to the exact target. Missing
  authentication, foreign origins and invalid request schemas were rejected.
  Two synthetic operations were prepared and cancelled without submitting;
  replaying a cancelled commit kept it cancelled, and the composer stayed empty.
  The assistant workspace resolves the updated portable Skill from its source.
- The production workspace was updated in place while retaining the unlocked
  original WeChat process. Browser checks at 1280px and 390px confirmed ready
  status and no page overflow; the action table scrolls inside its card. An
  unauthenticated Tailscale daemon can return null IPs; both the status response
  and UI now handle that state without interrupting action-list rendering.
- Harness was restarted separately to refresh MCP discovery; its plugin inventory
  reports the WeHarbor MCP plugin active. The original WeChat process was
  preserved, and no model request was made. Rechecking the three earlier approved
  sends found each marker exactly once; completed commit replays stayed sent,
  the composer was empty and a mismatched exact username was rejected.
- Image `sha256:3d74e20955a0c6349003355451c630859e30eba3172d6d12a8749655088ed332`
  was built from application revision
  `c730ca0137289016e5b68efb31ffbad7807b56b5`.
  Its full fresh-profile smoke test passed, including container restart,
  authentication, origin rejection, app switching, fourteen MCP tools,
  structured logged-out readiness, Harness RPC and original vendor file checks.
- The final image is loaded on the NAS. Nine updated runtime files match its
  hashes. The persistent override selects `weharbor:realtime-20261020-navigation`
  for the next recreation. The live container retains base image `b8fa1b571a93`
  and its original unlocked WeChat process; it was not recreated.

## October 20 unlocked-chat validation

- After the owner unlocked WeChat and selected the authorized one-to-one chat,
  original-process session proof and the unique database contact title matched.
  Qt marks both search and composer as multiline, so the driver now selects the
  unique editor within the titled chat pane. GI text/component/action calls use
  explicit interface dispatch to avoid Accessible method-name collisions.
- The installed WeChat paints Send without an AT-SPI button. The driver now
  recognizes the enabled caption locally with Tesseract, scoped to the right
  composer toolbar and green button. The two Chinese words scored above 93%
  in the deployment probe; acceptance requires at least 80% per word. X11/Qt
  frame geometry corrects the observed 2x DPI scale, and movement cancels clicks.
- One initial attempt stopped before submission when Send was absent from
  AT-SPI. Its action remains failed. Recovery checked that failure, exact owned
  test draft, session identity and visible Send, and cleared only that draft.
  No mouse send event occurred for that failed attempt.
- All three authorized marker messages then completed through HTTP prepare and
  commit. Each has a unique new self-message database receipt and occurs once
  in the selected chat. Replaying each completed commit kept its sent status
  and did not add a message. The composer is empty. A mismatched username was
  rejected by the current-session proof before typing.
- From observing the persisted submitted state to API visibility, bounded
  probes measured 1,791 ms, 1,735 ms and 2,082 ms. Polling adds uncertainty of
  about one 100 ms interval. The first two appeared before the commit receipt's
  two-second refresh; the third can include that refresh. These are outgoing
  self-message visibility checks, not independent incoming-message latency,
  recipient delivery or read receipts.
- Passed 98 integration/source tests, including low-confidence or incorrect
  Send captions and cancellation before all mouse events when a window moves.
  Image `sha256:cd573b40b1a19509e0a78397d9cdc479f86cd72aa1453e2b7ed1e5712661515e`
  was built from application revision `22b9f4b2c4b42c1dc294c39ea588d19dc5be8e87`.
  Its local fresh-profile smoke test passed, including restart, authentication,
  MCP discovery, app switching and unchanged original vendor package files.
  The image's English and Simplified Chinese OCR data are installed.
- The production driver was updated in place and only the workspace service
  restarted, preserving the unlocked WeChat process. The running container
  remains based on image `b8fa1b571a93`; its two driver source hashes and OCR
  dependencies match the new image. The full new image was loaded on the NAS
  and `compose.workspace.yml` now selects `weharbor:realtime-20261020-qt` for
  the next recreation. No container recreation occurred in this validation.

## October 20 event-sync and Harness update

- Analysis fork pinned to `f9be0a3a1bd0e9abfff5d1563ea29dbb35f28b24`: Linux
  DB/WAL notifications debounce for 150 ms, with a two-second fallback scan.
  Revision SSE checks run every 200 ms. The target is 1–3 seconds after a
  stable database write; decryption duration still limits actual latency.
- Passed 70 targeted analysis tests and 92 integration/source tests. The
  filesystem test exercises writes and rename replacement, while existing
  tests cover authenticated decryption, WAL recovery and publication failures.
- DSH `0.2.1-rc.2` was the official npm latest on October 20, 2026. A fresh
  local DSH profile successfully initialized the NAS MCP server and discovered
  twelve tools, including send preparation. No tool call or model request was
  made. The proxy now supports signed browser sessions, scoped cookies and
  the current settings RPC while preserving foreign-origin rejection.
- Browser verification against the official DSH bundle found that logical
  RPC channels must not be rewritten by the subpath proxy. JavaScript now
  passes through unchanged; a regression test exercises channel validation
  and one-time base-URI resolution. A fresh browser profile connects and
  displays model configuration without making a model request.
- Final image `sha256:b8fa1b571a93db07da9513678854382552722709c8bc55d7232fd1dfd36a10f8`
  was built from application revision `d248e9875f8421e34369cb90380f7b79381159de`.
  Fresh-profile smoke tests passed locally and on the NAS, including restart,
  browser authentication, origin rejection, MCP discovery and unchanged
  original WeChat/Alpha package files. The existing-profile container was
  replaced with this image and reports healthy.
- Production checks show filesystem-event monitoring with a two-second
  fallback, SSE ready, 26 synchronized databases and zero failed accounts.
  The actual NAS browser connects without a reconnect banner or console
  errors, and opens the API-key form. No key or model was configured. The
  Harness MCP plugin is active and exposes twelve tools. Protected integration
  state fingerprints match the backup.
- An isolated 8 KiB encrypted DB/WAL fixture on the NAS completed three
  authenticated decrypt/validated snapshot/SSE updates in 403 ms each. This
  verifies the synthetic event path; it does not establish latency for real
  messages or larger databases.
- Current-chat proof derives the session-name field from the installed
  original WeChat ELF metadata and handler code. It reads process memory
  without attaching a debugger or writing memory. Only an exact first-two-
  component version match is eligible; unsupported layouts fail closed. Live
  QObject ownership, unique page, stable reads, account, username and visible
  title are checked before UI actions.
- At the earlier image rollout the desktop asked for phone confirmation. The
  later unlocked-chat results above supersede that pending send check.

## October 20 earlier baseline

- Analysis fork pinned to `9ba2b71dc1b8018ab7feb59b028713beeb314f1b`.
  Linux snapshots publish revisions only after validated database replacement;
  SSE refreshes sessions and the selected chat, including after reconnect.
  Linux reads report their decrypted source without attempting native WCDB.
- Passed 59 targeted backend tests covering snapshot publication, failed
  decryption preservation, source selection, startup, WAL recovery and key
  modes, plus one frontend event-store test. The 78 integration/source checks
  also passed.
- Full final image build and fresh-profile smoke passed, including restart,
  browser authentication, origin protection, twelve MCP tools, app switching
  and unchanged original WeChat/Alpha packages.
- Existing profile retained; deployed container is healthy. Production checks
  through nginx confirmed automatic Linux snapshot updates are available, the
  refresh interval is 30 seconds, native WCDB was not probed, and the SSE ready
  event reports Linux snapshot mode. All 26 databases synchronized without
  failures. Read 1,029 sessions and a bounded sample of two messages; an actual
  V2 image decoded and returned HTTP 200 as a 7,157-byte JPEG.
- Installation is a secondary button inside app management: 12px text, 36px
  height, transparent background, no independent fixed positioning. Browser
  checks with simulated install eligibility confirmed one prompt invocation,
  hiding after consumption, and hiding with the menu. At 390 × 844 there was
  no horizontal overflow. On ordinary NAS HTTP the button stays hidden because
  the browser does not permit PWA installation there. No app was installed.

Synthetic database publication and frontend event tests verify the update
path. A newly received real message was not observed in an open chat during
this check; the production checks establish synchronization and event-stream
availability, rather than a native WCDB live connection.

The previous image remains tagged locally as `weharbor:before-realtime-20261020`.

## October 19 baseline

- Source validation: 78 tests, including preparation/commit, scheduling,
  idempotency, crash recovery, uncertain receipts, chat identity, remote-reader
  exclusion, local-source pinning, authenticated transport selection and failover.
- Analysis fork at `28ef68958969cd1cd7b50f49a7f03e8737ca6ee5`: 85 targeted tests
  covering Linux snapshots, startup, key handling, image decryption and source
  selection, with seven upstream/dependency warnings.
- Full image build and fresh-profile smoke test, including container restart,
  existing browser authentication, CSRF protection, app switching, profile
  permissions and unchanged original WeChat/Alpha packages.
- Authenticated Harness RPC successfully listed a directory through the public
  prefix; foreign-origin RPC returned 403. The HTML compatibility layer supplies
  randomUUID on NAS HTTP without changing the official Harness bundle.
- Browser at 390 × 844: fullscreen view switching, persistent iframes, no
  horizontal overflow in the tested views, working analysis agreement page, and
  Harness directory selection plus creation of an empty synthetic session.
  The analysis agreement was displayed without accepting it on the user's behalf.
- Existing-profile read-only validation: 26 databases synchronized with zero
  failures; one account, 1,028 sessions and a bounded sample of two messages read.
  Existing WeFlow DB and image keys were reused and verified. One actual V2 image
  decoded as a 2,839-byte JPEG and returned HTTP 200 through the media API.
  Generated avatar URLs preserve `/analysis/api/`.
- Twelve MCP tools listed; the portable Skill loaded through HTTP and MCP
  resources. Harness performed MCP initialization and tool discovery.

## Pending checks for the preceding deployed baseline

The driver has now passed the authorized real-chat tests above and exact-target
navigation through the accessible Contacts search results. It does not send
attachments, quoted replies, mentions or forwards. Independent incoming-message latency, recipient delivery
and read receipts remain unverified.

Model dialogue awaits Harness model credentials. Tailscale login and named
Cloudflare Tunnel credentials/DNS await the owner's configuration. Their
binaries and settings UI are present; no working external route is claimed.
Direct NAS HTTP was verified; a separate public domain was not configured.

Existing WeFlow keys were sufficient, so GDB capture/re-login was not exercised
against the production account. Linux capture and image paths have targeted
tests; not every historical attachment format was tested on real data.

## Deployment and rollback

The existing Compose file is kept intact; a `compose.workspace.yml` override
selects the locally built image without pulling it. The original profile volume
is preserved. Before deploying, the original Compose configuration and private
container metadata were backed up, and the previous image was tagged locally.
Keep that backup and image until the pending account/model/network checks pass.
The event-sync rollout backup is `event-sync-20261020-064151` under the private
deployment backup directory. The preceding image remains tagged
`weharbor:before-fast-sync-20261020`; the intermediate Harness integration
image is also retained as `weharbor:before-harness-fix-20261020`.
The Qt Send update backup is `qt-send-20261020-081901` in that directory, with
the preceding override and a hash-only image/source manifest. Its base image
is retained as `weharbor:before-qt-send-20261020`. The in-place desktop driver
backup is `/config/.local/share/weharbor/desktop-before-qt-controls.py` inside
the production container. Recreating from the selected new image preserves the
profile volume but restarts WeChat, so it was staged rather than forced while
the owner's unlocked chat was in use.

The later navigation rollout backup is `navigation-20261020-102426` under the
same private deployment backup directory. It retains the preceding override
and hash-only manifest. `weharbor:before-navigation-20261020` retains the Qt
image. The pre-navigation runtime files and private action-database backup are
inside `/config/.local/share/weharbor/before-navigation-20261020-100304` in the
production container. A runtime-only rollback should restore the saved program
files while the workspace service is stopped, then restart that service; do not
replace the live action database with an older backup. This preserves subsequent
operation records and the unlocked WeChat session.

No combined image was published. Upstream analysis licensing and the vendor
redistribution conditions in `THIRD_PARTY_NOTICES.md` still require clarification
before publishing one.
