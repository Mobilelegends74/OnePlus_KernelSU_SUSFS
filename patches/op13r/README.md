# OP13R performance feature patches

These patches target the OnePlus Android 14 Linux 6.1 common kernel selected by
`manifests/a15/oneplus_13r_v.xml` at source revision
`7b9a23054ab0ada2886ed34a2137b9d0312891ff`.

## Android LTS 6.1.176 uprev

`0000-linux-6.1.118-to-6.1.176.patch.xz` updates the pinned OnePlus Linux
6.1.118 source to the Android 14 Linux 6.1.176 LTS level before any local
KernelSU, SUSFS or performance patches are applied. The delta is based on the
official Android common range below and resolves overlapping changes in favor
of the newer OnePlus F2FS and Android KABI adaptations.

- Android 6.1.118 base tag:
  `2f2512ac1091bb2b28c20306fa86d890e8f3f01f`
- Android 6.1.176 LTS merge:
  `2cee2416baae662580c7ce03bbe53d1c8f23d203`
- Compressed patch SHA-256:
  `0208cf96d88a2a6fb94399909e8f1b34c46e16ad95114a3b2cdbe0072cfac229`

Upstream: <https://android.googlesource.com/kernel/common/+/2f2512ac1091bb2b28c20306fa86d890e8f3f01f..2cee2416baae662580c7ce03bbe53d1c8f23d203>

## BORE

`0001-sched-bore-5.3.0-android14-6.1.patch` integrates the BORE 5.3.0 scheduler
logic for the classic CFS implementation used by this Android kernel. Scheduler
state is stored in the existing Android KABI reserves of `struct sched_entity`.
BORE is enabled by `CONFIG_SCHED_BORE=y` and remains configurable through its
`kernel.sched_*` sysctls.

Upstream: <https://github.com/firelzrd/bore-scheduler>

Android 6.1 port reference:
<https://github.com/Mohithash/kernel_xiaomi_sm8635/tree/peridot-6.1.175>

## LZ4KD

`0002-lz4kd-zram-android14-6.1.patch` connects LZ4KD to the kernel compression
API and ZRAM. The implementation files are fetched from `SukiSU_patch` at the
pinned commit `547ae94bcaec53d030398f857950c64662043a5d`; unrelated upstream module
blacklist changes are deliberately not included.

## OnePlus HybridSwap LZ4K

`0003-op13r-force-zram-lz4k.patch` handles the custom OnePlus HybridSwap ZRAM
driver that remains on the device vendor partition. The closed OxygenOS vendor
initialization writes `lz4` to `zram0/comp_algorithm` before creating the ZRAM
device. For this OP13R-only configuration, the patch changes just that request
to the already available OnePlus `lz4k` backend. Other compressor requests,
ZRAM sizing and all HybridSwap controls remain unchanged.

The OP13R configuration keeps `CONFIG_CRYPTO_LZ4KD=y` available to the kernel
compression API and enables `CONFIG_OP13R_FORCE_ZRAM_LZ4K=y` for the active
OnePlus HybridSwap ZRAM device.

Upstream: <https://github.com/SukiSU-Ultra/SukiSU_patch>
