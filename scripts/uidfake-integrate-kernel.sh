#!/usr/bin/env bash
# Integrate pinned HMA UID Fake as CONFIG_HMA_UIDFAKE_BUILTIN=y.
set -euo pipefail
kernel="${1:?pass path to checked-out common kernel source}"
test -f "$kernel/drivers/misc/Kconfig"
test -f "$kernel/drivers/misc/Makefile"
test -f "$kernel/arch/arm64/configs/gki_defconfig"
repo="https://github.com/Mobilelegends74/hma-uidfake.git"
commit="fa72fe4fa93b26a336bf8c421ba60a108a54c253"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --quiet --filter=blob:none "$repo" "$work/upstream"
git -C "$work/upstream" checkout --quiet --detach "$commit"
test "$(git -C "$work/upstream" rev-parse HEAD)" = "$commit"
dest="$kernel/drivers/misc/hma_uidfake"
mkdir -p "$dest/include"
for name in main.c patch.c hooks.c lsm.c netlink.c policy.c; do
  cp "$work/upstream/src/$name" "$dest/$name"
done
for name in kaux.h kmi_compat.h uidfake.h; do
  cp "$work/upstream/src/include/$name" "$dest/include/$name"
done
cat > "$dest/Makefile" <<'EOF'
# Built-in HMA UID Fake, never a loadable kernel module.
obj-$(CONFIG_HMA_UIDFAKE_BUILTIN) += hma_uidfake.o
hma_uidfake-y := main.o patch.o hooks.o lsm.o netlink.o
ccflags-y += -I$(src)/include -I$(src)
EOF
cat > "$dest/Kconfig" <<'EOF'
config HMA_UIDFAKE_BUILTIN
    bool "HMA UID Fake built into kernel"
    depends on ARM64 && KPROBES && NET
    help
      In-kernel UID-visibility policy engine. A userspace sync service
      supplies HMA/HMA-OSS policy using the existing kaux netlink protocol.
      This code is built into Image and does not generate a .ko.
EOF
grep -qF 'source "drivers/misc/hma_uidfake/Kconfig"' "$kernel/drivers/misc/Kconfig" ||
  printf '\nsource "drivers/misc/hma_uidfake/Kconfig"\n' >> "$kernel/drivers/misc/Kconfig"
grep -qF 'obj-$(CONFIG_HMA_UIDFAKE_BUILTIN) += hma_uidfake/' "$kernel/drivers/misc/Makefile" ||
  printf '\nobj-$(CONFIG_HMA_UIDFAKE_BUILTIN) += hma_uidfake/\n' >> "$kernel/drivers/misc/Makefile"
printf '\nCONFIG_HMA_UIDFAKE_BUILTIN=y\n' >> "$kernel/arch/arm64/configs/gki_defconfig"
echo "UIDFAKE: source at $commit integrated into kernel tree."
