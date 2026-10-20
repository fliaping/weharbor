# Workspace validation — 2026-10-20

Validated on an amd64 Linux NAS with an existing WeHarbor profile. Test output
contains counts and status only; keys, chat contents and account identities are
not committed. The locally deployed image is
`sha256:5e7b6ef5b43e12e135251d23f51076e6b81a540c507a43e2c59584f67ceb5d7c`.
The advanced build below is local and has not replaced that NAS deployment.

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

## October 20 update

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

The running desktop exposes 169 accessibility nodes and asks for phone
confirmation. No real message was prepared or sent. The independent AT-SPI
driver still needs validation against a logged-in real chat, with an explicitly
authorized recipient and text. It currently requires that target chat to be
selected; it does not automatically navigate arbitrary chats or attachments.
Synthetic receipts do not establish real recipient delivery.

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

No combined image was published. Upstream analysis licensing and the vendor
redistribution conditions in `THIRD_PARTY_NOTICES.md` still require clarification
before publishing one.
