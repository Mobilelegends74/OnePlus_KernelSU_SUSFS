#!/system/bin/sh
# Non-module KernelSU service.d daemon, installed by the UIDFAKE kernel flash ZIP.
BASE=/data/adb/uidfake-kernel
LOG="$BASE/sync.log"
[ -x "$BASE/sync-tool" ] || exit 0
mkdir -p "$BASE"
chmod 700 "$BASE"
"$BASE/sync-tool" >> "$LOG" 2>&1 &
