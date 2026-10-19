#!/usr/bin/env bash
# Reproduces the proot-apps evaluation in docs/proot-apps-evaluation.md.
# Usage: tests/proot/run-proot-eval.sh   (needs docker, downloads/alpha.deb, gcc)
set -euo pipefail
cd "$(dirname "$0")"
DOCKER=${DOCKER:-"sudo -n docker"}
BASE=$(jq -r .base_image ../../versions.lock.json)
PROOT_NEXT_URL=https://github.com/selkies-project/proot-next/releases/download/0.3.2/proot-x86_64
PROOT_NEXT_SHA=27361a306817d5062b092fbde6c0debbb2f3f77a4fed884256bd1e17cf4c982e
W=$(mktemp -d /tmp/weharbor-proot-eval.XXXX); chmod 755 "$W"
gcc -static -O1 -o "$W/target" target.c
gcc -static -O1 -o "$W/reader" reader.c
cp Dockerfile.alpha ../../downloads/alpha.deb "$W/"
curl -fsSLo "$W/proot-next" "$PROOT_NEXT_URL"; echo "$PROOT_NEXT_SHA  $W/proot-next" | sha256sum -c -; chmod +x "$W/proot-next"
$DOCKER build -q -t weharbor-proot-eval-alpha -f "$W/Dockerfile.alpha" "$W" >/dev/null
mkdir "$W/rootfs"; cid=$($DOCKER create weharbor-proot-eval-alpha /bin/true)
$DOCKER export "$cid" | sudo -n tar -x -C "$W/rootfs"; $DOCKER rm "$cid" >/dev/null
sudo -n chown -R 911:911 "$W/rootfs"
D=/opt/Alpha/resources/bin
echo "### Alpha runtime guard, native (no proot)"
$DOCKER run --rm weharbor-proot-eval-alpha sh -c "for b in alpha_xkey_helper alpha-key-worker; do $D/\$b --guard-self-check 2>&1 | grep -o '\"status\":[-0-9]*'; done"
cat > "$W/inner.sh" <<IN
#!/bin/bash
for P in /proot-apps/proot /w/proot-next; do for np in 0 1; do
  echo "### Alpha runtime guard under \$P PROOT_NO_PTRACE=\$np"
  for b in alpha_xkey_helper alpha-key-worker; do PROOT_NO_PTRACE=\$np \$P -R /w/rootfs $D/\$b --guard-self-check 2>&1 | grep -o '"status":[-0-9]*\|Error.*'; done
done; done
for P in /proot-apps/proot /w/proot-next; do
  echo "### WeChat-like target under \$P <- native reader"
  rm -f /w/rootfs/tmp/i /tmp/i; \$P -R /w/rootfs /usr/local/bin/target /tmp/i & sleep 2
  cat /w/rootfs/tmp/i /tmp/i 2>/dev/null | head -1 > /tmp/info; /w/rootfs/usr/local/bin/reader /tmp/info | sed 's/^/   /'
  pkill -f /usr/local/bin/target || true; sleep 1
done
IN
chmod +x "$W/inner.sh"
$DOCKER run --rm --cap-add SYS_PTRACE -v "$W:/w" --entrypoint bash "$BASE" -c 'su -s /bin/bash abc -c /w/inner.sh' 2>&1 | grep -v Terminated
sudo -n rm -rf "$W"
