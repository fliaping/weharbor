# proot-apps evaluation (WeChat + Alpha)

Status: **rejected for Alpha; not adopted for WeChat**. WeHarbor keeps installing
the unmodified official WeChat deb and the unmodified Alpha deb natively in the
image (see `Dockerfile`, `versions.lock.json`).

Evaluated 2026-10-19 (UTC+8) against the pinned base
`ghcr.io/linuxserver/baseimage-selkies:debiantrixie@sha256:5b3f1045…`, which ships
proot-apps 0.5.3 with classic **PRoot 5.1.0** in `/proot-apps` (copied to
`/config/.local/bin` at start; apps land in `/config/proot-apps`). proot-next
0.3.2 (`selkies-project/proot-next`) was tested too. Reproduce with
`tests/proot/run-proot-eval.sh`.

## What proot-apps offers

* Catalog app `wechat` exists, but it downloads the floating
  `WeChatLinux_x86_64.AppImage` at image build time: not pinned to 4.1.13.23 and
  not the official deb. No Alpha app exists.
* Custom apps: `proot-apps build-install-local <dir>` builds a Dockerfile
  (`FROM ghcr.io/linuxserver/proot-apps:debian-trixie`, `/entrypoint`), saves it
  and unpacks the top layer into `$HOME/proot-apps/<image>/`. Each app is its own
  rootfs and every `proot-apps run` is a separate proot session. Building an
  app needs Docker (not available inside the container), so in-container
  install would mean publishing our own image to a registry.

## Findings

| Test | Result |
| --- | --- |
| `alpha_xkey_helper --guard-self-check`, `alpha-key-worker --guard-self-check`, native | `status 0` |
| same under PRoot 5.1.0 (ptrace mode or `PROOT_NO_PTRACE=1`) | `status -103`, `KEY_RUNTIME_POLICY_REJECTED` |
| same under proot-next 0.3.2 (both modes; TracerPid hidden) | `status -103`, `KEY_RUNTIME_POLICY_REJECTED` |
| native reader → process in PRoot 5.1.0: `process_vm_readv`, `/proc/pid/mem` | works |
| native reader → process in PRoot: `PTRACE_ATTACH` / `PTRACE_SEIZE` | `EPERM` (already traced by proot) |
| native reader → process in PRoot: `/proc/pid/exe` | `/tmp/prooted-<pid>-XXXX` (loader alias, not WeChat's binary) |
| reader and target in separate proot sessions (same or different rootfs) | memory read works, ptrace fails |
| reader and target in the same PRoot 5.1.0 session | memory read and emulated `PTRACE_ATTACH` work |

The Alpha runtime guard (alpha-guard-sdk 2.1.0) refuses to run its key
acquisition under any proot variant. Even running the helper natively through
an explicit `ld.so` invocation trips it, so it checks the process image/loader,
not just `TracerPid`. Because of that, Alpha cannot be a proot app. This is a
property of Alpha's closed-source binaries, and we cannot change it without
modifying them.

WeChat alone could run as a proot app with Alpha native, but it does not pay
off:

* the proot loader alias in `/proc/<pid>/exe` and proot's own ptrace hold on
  WeChat break assumptions a key extractor typically makes (ptrace attach,
  locating the WeChat binary). We could not confirm that Alpha still gets the
  key without a logged-in session;
* every WeChat syscall that touches a path pays PRoot's ptrace cost;
* the catalog app is unpinned, and a pinned custom app would need either a
  build-time unpack (no gain over the native deb) or a registry image we would
  have to publish and maintain.

## Recommendation

Keep both WeChat and Alpha native in the image (current `feat/selkies2-alpha`
design). proot-apps remains available in the base for optional, unrelated
desktop apps the user wants to add to `/config/proot-apps`.
