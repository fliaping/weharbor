# Workspace validation — 2026-10-19

Validated on an amd64 Linux NAS with an existing WeHarbor profile. Test output
contains counts and status only; keys, chat contents and account identities are
not committed. The locally deployed image is
`sha256:51fccda88e2e124d59ff1e88d1b7333354118a5cc3198b420020fccd1e2f2063`.

## Passed

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
