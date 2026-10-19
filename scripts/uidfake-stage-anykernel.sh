#!/usr/bin/env bash
# Package the source patch and automatically installed Android sync companion.
set -euo pipefail
ak3="${1:?pass AnyKernel3 directory}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
artifact="$(mktemp)"
trap 'rm -f "$artifact"' EXIT
curl -fLsS --retry 5 --connect-timeout 25 \
  https://github.com/Mobilelegends74/hma-uidfake/releases/download/v0.3.6-fork/hma-uidfake-fork-0.3.6.zip \
  -o "$artifact"
echo "d0315a3acde5cb11969aad6fa76be0d42bbbbcbfb225f61410017d08791272f9  $artifact" | sha256sum -c -
mkdir -p "$ak3/uidfake"
unzip -p "$artifact" sync-tool > "$ak3/uidfake/sync-tool"
echo "efb4c77c11ea55e961024e6fe4d6fd1999dc281be2e11db3646939c546e3382f  $ak3/uidfake/sync-tool" | sha256sum -c -
chmod 755 "$ak3/uidfake/sync-tool"
cp "$root/scripts/uidfake-kernel-service.sh" "$ak3/uidfake/service.sh"
cp "$root/uidfake/hma-uidfake-native.patch" "$ak3/uidfake/"
cp "$root/docs/uidfake-op13r.md" "$ak3/uidfake/README.md"
cp "$root/uidfake/LICENSE" "$root/uidfake/NOTICE" "$ak3/uidfake/"
python3 - "$ak3/anykernel.sh" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
anchor = '# boot install\n'
if s.count(anchor) != 1:
    raise SystemExit('Unexpected AnyKernel3 boot-install anchor')
install = '''
# UIDFAKE companion preflight: do not flash a silently incomplete installation.
[ -d /data/adb ] && [ -w /data/adb ] ||
  abort "UIDFAKE: flash from booted rooted Android with writable /data/adb"
for module in /data/adb/modules/*; do
  [ -d "$module" ] || continue
  [ -f "$module/disable" ] && continue
  [ -f "$module/remove" ] && continue
  if [ -f "$module/ko/android14-6.1_arm64_hma_uidfake.ko" ] ||
     [ -f "$module/hma_uidfake.ko" ]; then
    abort "UIDFAKE: disable the separate UIDFAKE LKM module before flashing"
  fi
done
mkdir -p /data/adb/uidfake-kernel /data/adb/service.d ||
  abort "UIDFAKE: cannot create sync directories"
cp -f uidfake/sync-tool /data/adb/uidfake-kernel/sync-tool ||
  abort "UIDFAKE: cannot install sync-tool"
cp -f uidfake/service.sh /data/adb/uidfake-kernel/service.sh ||
  abort "UIDFAKE: cannot install service"
cp -f uidfake/service.sh /data/adb/service.d/97-uidfake-kernel.sh ||
  abort "UIDFAKE: cannot install boot service"
chmod 0700 /data/adb/uidfake-kernel
chmod 0755 /data/adb/uidfake-kernel/sync-tool /data/adb/uidfake-kernel/service.sh /data/adb/service.d/97-uidfake-kernel.sh
ui_print "UIDFAKE built-in and automatic HMA sync installed"
'''
p.write_text(s.replace(anchor, install + '\n' + anchor))
PY
echo "UIDFAKE: built-in patch and checksum-verified sync companion packaged"
