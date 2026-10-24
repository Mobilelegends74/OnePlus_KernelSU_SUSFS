#!/usr/bin/env bash
# Apply the reviewed PR 3938 backport, never silently skip an incompatible tree.
set -euo pipefail
ksu_tree="$(realpath "${1:?Usage: apply-selinux-timing.sh KSU_TREE}")"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
patch_file="$project_root/patches/selinux/0001-ksu-reduce-selinux-hide-timing.patch"
test -f "$ksu_tree/kernel/feature/selinux_hide.c"
cd "$ksu_tree"
if git apply --check "$patch_file" 2>/dev/null; then
    git apply "$patch_file"
    echo 'Applied KernelSU SELinux timing backport (PR 3938).'
elif git apply --reverse --check "$patch_file" 2>/dev/null; then
    echo 'KernelSU SELinux timing backport already present.'
else
    echo '::error::PR 3938 backport does not match this KernelSU source; review required.' >&2
    git apply --check "$patch_file" >&2 || true
    exit 1
fi
