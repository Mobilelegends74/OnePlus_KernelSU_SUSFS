#!/usr/bin/env bash
# Add userspace policy sync to the kernel's AnyKernel3 package (not a KSU module).
set -euo pipefail
ak3="${1:?pass AnyKernel3 dir}"
test -f "$ak3/anykernel.sh"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
artifact="$(mktemp)"
trap 'rm -f "$artifact"' EXIT
curl -fLsS --retry 5 --connect-timeout 25 \
  "https://github.com/Mobilelegends74/hma-uidfake/releases/download/v0.3.6-fork/hma-uidfake-fork-0.3.6.zip" \
  -o "$artifact"
unzip -t "$artifact" >/dev/null
mkdir -p "$ak3/uidfake"
if unzip -Z1 "$artifact" | grep -qx 'sync-tool'; then
  unzip -p "$artifact" sync-tool > "$ak3/uidfake/sync-tool"
elif unzip -Z1 "$artifact" | grep -qx 'bin/sync-tool'; then
  unzip -p "$artifact" bin/sync-tool > "$ak3/uidfake/sync-tool"
else
  echo "::error::Pinned uidfake release does not contain sync-tool" >&2
  unzip -Z1 "$artifact" | head -n 100
  exit 1
fi
test -s "$ak3/uidfake/sync-tool"
chmod 755 "$ak3/uidfake/sync-tool"
cp "$repo_root/scripts/uidfake-kernel-service.sh" "$ak3/uidfake/service.sh"
chmod 755 "$ak3/uidfake/service.sh"
cat >> "$ak3/anykernel.sh" <<'EOF'

# HMA UID Fake built-in: install policy sync without a KernelSU module.
# Encrypted/locked /data cannot be modified at flashing time.
if [ -d /data/adb ] && [ -w /data/adb ]; then
  mkdir -p /data/adb/uidfake-kernel /data/adb/service.d
  cp -f uidfake/sync-tool /data/adb/uidfake-kernel/sync-tool
  cp -f uidfake/service.sh /data/adb/service.d/97-uidfake-kernel.sh
  chmod 0700 /data/adb/uidfake-kernel
  chmod 0755 /data/adb/uidfake-kernel/sync-tool /data/adb/service.d/97-uidfake-kernel.sh
  ui_print "UIDFAKE built in; HMA auto-sync service installed"
else
  ui_print "UIDFAKE WARNING: /data/adb inaccessible; auto-sync service not installed"
  ui_print "Flash from a booted, rooted Android environment for full auto-sync."
fi
EOF
echo "UIDFAKE: packaged pinned sync-tool and service for kernel ZIP."
