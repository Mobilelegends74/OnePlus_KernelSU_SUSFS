# HMA UIDFAKE native integration — OnePlus 13R

Branch: `UIDFAKE-op13r-6.1.118-build80`. Baseline: build80-1,
Linux 6.1.118 / OxygenOS 15, NoMount stable v2.1.1.
Status: experimental; successful compilation is not a device boot test.

## Sources and reusable patch

- `uidfake/kernel/`: native component, Kconfig and Kbuild.
- `uidfake/hma_uidfake.h`: internal kernel API with CONFIG=n stubs.
- `uidfake/hma-uidfake-native.patch`: complete source patch, including call sites.
- `scripts/uidfake-native-integrate.py`: checked, idempotent source integration
  and patch generation for kernels whose context differs from the supplied patch.
- HMA protocol/header and netlink implementation originate from
  [hma-uidfake fa72fe4](https://github.com/Mobilelegends74/hma-uidfake/tree/fa72fe4fa93b26a336bf8c421ba60a108a54c253),
  released as v0.3.6-fork, GPL-2.0. Native core and integration are maintained here.

Apply to a clean kernel source tree:

```sh
patch -p1 < hma-uidfake-native.patch
# Enable CONFIG_HMA_UIDFAKE_BUILTIN=y using the kernel's normal defconfig process.
```

Alternatively run `python3 scripts/uidfake-native-integrate.py KERNEL_DIR`.
This requires the complete uidfake directory from this repository and performs
all anchor checks before writing. It does not silently skip an unsupported API.
The CI wrapper also enables CONFIG_HMA_UIDFAKE_BUILTIN=y in gki_defconfig.

## Architecture

The bool option links core.o and netlink.o into Image. There is no .ko,
module loader, instruction scanner, kprobe dependency, syscall-table patch,
f_op replacement or use of spare scheduler flags.
Header paths are rooted at srctree and support separate O= output directories.

Native calls in kernel/sys.c and block/ioprio.c filter PRIO_USER /
IOPRIO_WHO_USER for getpriority, setpriority, ioprio_get and ioprio_set.
They use the existing ESRCH path and balanced RCU exits. The common C syscall
implementations also cover the compat ABI. Existing capability, LSM, namespace
and argument checks remain in their normal code paths.

commit_creds records the app identity only on successful credential publication.
A dedicated fork-inherited task_struct field replaces the LKM's thread_info
bit packing. App-zygote descendants retain their identity. Unnamed isolated
children are attributed from a successfully security-checked file open and
the HMA companion's installed-code inode map. The first UID query closes an
unresolved attribution window. Later UID changes cannot select another identity.

The native implementation uses sorted RCU policy snapshots and binary search,
retaining caller/target rules, wildcard caller, protected system UIDs and the
upstream app-id caller semantics. Targets use kernel-mapped full UIDs.
It intentionally does not carry over instruction-dependent hash mirroring or
the LKM's timing-equalization algorithm: constant-time indistinguishability
against microbenchmarks is **not claimed**.
Policy and APK updates publish complete validated snapshots. Malformed updates,
allocation failures and unresolved APK paths keep the preceding snapshot.

Generic netlink preserves the published kaux protocol v4 and status layout.
Only root with the existing GENL_ADMIN_PERM permission in the initial network
namespace can upload. CRC, size/alignment, upload-owner and page-order checks
are enforced. Empty policy uploads explicitly revoke all rules.

## Automatic Android synchronization

A kernel cannot safely parse an app's encrypted credential-protected JSON.
The ZIP therefore includes the existing ARM64 Android sync-tool, but none of
the upstream LKM/module installer. Its release archive and extracted executable
are both verified against fixed SHA-256 digests.

AnyKernel installs the helper and supervisor under /data/adb/uidfake-kernel
and a boot script under /data/adb/service.d before flashing the kernel.
The existing root environment's service.d runner starts it on subsequent boots.
There is no UIDFAKE KernelSU module, insmod or manual rule copy.
The supervisor retries crashes; the helper waits for credential storage,
watches configuration/preset/package changes and uploads the resolved policy.

The companion supports these upstream sources, in priority order:

1. Existing optional /data/adb/hma-uidfake/config.json.
2. Existing legacy /data/adb/modules/hma-uidfake/config.json.
3. HMA: /data/user/0/com.tsng.hidemyapplist/files/config.json
   (with /data/data fallback).
4. HMA-OSS: /data/misc/hide_my_applist_*/config.json or
   /data/system/hide_my_applist_*/config.json.

No native config is created by the kernel installer. An existing explicit native
config intentionally takes priority, as in upstream. Multi-user HMA config
discovery is limited by the upstream helper's user-0 paths; arbitrary Android
user/profile support has not been implemented or claimed.

The kernel patch itself has no KernelSU dependency. The supplied OP13R boot
adapter uses the service.d facility already present in this KernelSU kernel.
For other ROM/root distributions the builder must provide a privileged boot
runner (Android init can execute uidfake-kernel/service.sh); no universal
Android boot-runner ABI exists. This distribution adaptation cannot be replaced
by a kernel Kconfig option. SELinux enforcement remains enabled.

If writable /data/adb is unavailable, the installer aborts before writing boot.
It also rejects an enabled separate UIDFAKE LKM module. Existing user rules are
preserved. Ordinary HMA/HMA-OSS app/LSPosed prerequisites remain their own.

## Validation and remaining device tests

- Host ASan/UBSan tests compile the actual native core, exercising caller rules,
  wildcard, isolation/inheritance, revocation, malformed APK data and OOM retention.
- Source integrator checks all native call sites and is idempotent.
- CI checks the final CONFIG_HMA_UIDFAKE_BUILTIN=y and builds Image.
- The ZIP is marked _UIDFAKE and contains the companion, service, README and patch.
- On the phone still verify boot, SELinux denials, service autostart after reboot,
  HMA/HMA-OSS edits, app-zygote and system-zygote isolation, compat apps and
  removal of rules. Log: /data/adb/uidfake-kernel/sync.log.
- task_struct gains one conditional field at its end on the ARM64 target,
  preserving existing member offsets but changing the structure's total size.
  Vendor/KMI compatibility and other architectures need independent validation.
- Source anchors avoid Android/Linux version-number checks; a successful OP13R
  build does not prove compatibility with every kernel version or OEM.
