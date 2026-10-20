# Workspace validation — 2026-10-20

Validated on an amd64 Linux NAS with an existing WeHarbor profile. Test output
contains counts and status only; keys, chat contents and account identities are
not committed. The locally deployed image is
`sha256:5e7b6ef5b43e12e135251d23f51076e6b81a540c507a43e2c59584f67ceb5d7c`.

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

## Pending deployment checks

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
